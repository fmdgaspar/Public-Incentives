#!/usr/bin/env python3
"""
Script para carregar dados das empresas do CSV para a base de dados.

Este script:
1. Lê o ficheiro companies_sample.csv
2. Normaliza os dados (CAE codes, localização, tamanho)
3. Gera embeddings para as empresas
4. Carrega tudo na base de dados

Usage:
    python -m backend.app.scripts.load_companies [--csv-path PATH] [--limit N]
"""

import sys
import argparse
import csv
import re
from pathlib import Path
from typing import List, Dict, Optional, Set
from decimal import Decimal

import structlog
from dotenv import load_dotenv

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

load_dotenv()

from backend.app.db.session import SessionLocal
from backend.app.models.company import Company, CompanyEmbedding
from backend.app.services.openai_client import ManagedOpenAIClient
from scraper.extractors.embedding_service import EmbeddingService

logger = structlog.get_logger()


def parse_cae_codes(cae_field: str) -> List[str]:
    """
    Parse CAE codes from CSV field.
    
    Args:
        cae_field: Raw CAE field from CSV
        
    Returns:
        List of normalized CAE codes (4-5 digits)
    """
    if not cae_field or cae_field.strip() == '':
        return []
    
    # Extract all 4-5 digit codes
    codes = re.findall(r'\b\d{4,5}\b', str(cae_field))
    
    # Normalize to 4-5 digits, zero-pad if needed
    normalized = []
    for code in codes:
        # Remove leading zeros and ensure 4-5 digits
        clean_code = code.lstrip('0')
        if len(clean_code) < 4:
            clean_code = clean_code.zfill(4)
        elif len(clean_code) > 5:
            clean_code = clean_code[:5]
        
        if clean_code not in normalized:
            normalized.append(clean_code)
    
    return normalized


def determine_company_size(employees: Optional[int], turnover: Optional[float]) -> str:
    """
    Determine company size based on employees and turnover.
    
    Args:
        employees: Number of employees
        turnover: Annual turnover in EUR
        
    Returns:
        Company size: 'micro', 'pme', 'grande', or 'unknown'
    """
    if employees is not None:
        if employees < 10:
            return 'micro'
        elif employees < 250:
            return 'pme'
        else:
            return 'grande'
    
    if turnover is not None:
        # Convert to EUR (assuming turnover is in thousands)
        turnover_eur = turnover * 1000
        if turnover_eur < 2_000_000:  # < 2M EUR
            return 'micro'
        elif turnover_eur < 50_000_000:  # < 50M EUR
            return 'pme'
        else:
            return 'grande'
    
    return 'unknown'


def extract_location(postal_code: str, district: str = None) -> Dict[str, Optional[str]]:
    """
    Extract location information from postal code.
    
    Args:
        postal_code: Portuguese postal code (e.g., "3050-419")
        district: District field (contains names, not location)
        
    Returns:
        Dict with district, county, parish
    """
    location = {
        'district': None,
        'county': None,
        'parish': None
    }
    
    if postal_code and len(postal_code) >= 4:
        # Portuguese postal codes: XXXX-XXX
        # First 4 digits can help identify district
        try:
            code = postal_code.replace('-', '')[:4]
            
            # Simplified mapping of postal code prefixes to districts
            # This is a basic mapping - in production you'd use a proper database
            postal_to_district = {
                '1000': 'Lisboa', '1100': 'Lisboa', '1200': 'Lisboa', '1300': 'Lisboa',
                '2000': 'Santarém', '2100': 'Santarém', '2200': 'Santarém',
                '3000': 'Coimbra', '3100': 'Coimbra', '3200': 'Coimbra',
                '4000': 'Porto', '4100': 'Porto', '4200': 'Porto', '4300': 'Porto',
                '5000': 'Vila Real', '5100': 'Vila Real',
                '6000': 'Castelo Branco', '6100': 'Castelo Branco',
                '7000': 'Évora', '7100': 'Évora',
                '8000': 'Faro', '8100': 'Faro', '8200': 'Faro', '8300': 'Faro',
                '9000': 'Funchal', '9100': 'Funchal',
                '9500': 'Ponta Delgada', '9600': 'Ponta Delgada'
            }
            
            # Find the closest match
            for prefix, district_name in postal_to_district.items():
                if code.startswith(prefix[:2]):  # Match first 2 digits
                    location['district'] = district_name
                    break
            
            # If no match found, use a generic location
            if not location['district']:
                location['district'] = 'Portugal'
                
        except:
            location['district'] = 'Portugal'
    else:
        location['district'] = 'Portugal'
    
    return location


def create_company_text(company: Dict) -> str:
    """
    Create text representation of company for embedding.
    
    Args:
        company: Company data dictionary
        
    Returns:
        Text string for embedding
    """
    parts = []
    
    # Company name
    if company.get('name'):
        parts.append(company['name'])
    
    # CAE codes
    if company.get('cae_codes'):
        cae_str = ', '.join(company['cae_codes'])
        parts.append(f"CAE: {cae_str}")
    
    # Location
    location_parts = []
    if company.get('district'):
        location_parts.append(company['district'])
    if company.get('county'):
        location_parts.append(company['county'])
    if location_parts:
        parts.append(f"Localização: {'/'.join(location_parts)}")
    
    # Description
    if company.get('description'):
        parts.append(company['description'])
    
    return '. '.join(parts)


def load_companies_from_csv(
    csv_path: str,
    limit: Optional[int] = None,
    force: bool = False
) -> Dict:
    """
    Load companies from CSV file.
    
    Args:
        csv_path: Path to CSV file
        limit: Maximum number of companies to process
        force: Force reload even if companies exist
        
    Returns:
        Statistics dictionary
    """
    logger.info("loading_companies_started", csv_path=csv_path, limit=limit, force=force)
    
    # Initialize services
    openai_client = ManagedOpenAIClient()
    embedding_service = EmbeddingService(openai_client)
    
    with SessionLocal() as db:
        # Check if companies already exist
        existing_count = db.query(Company).count()
        if existing_count > 0 and not force:
            logger.info("companies_already_exist", count=existing_count)
            return {
                'total': existing_count,
                'loaded': 0,
                'skipped': existing_count,
                'errors': 0,
                'total_cost_eur': 0.0
            }
        
        # Clear existing data if force
        if force and existing_count > 0:
            logger.info("clearing_existing_companies", count=existing_count)
            db.query(CompanyEmbedding).delete()
            db.query(Company).delete()
            db.commit()
        
        # Read CSV
        companies_loaded = 0
        companies_skipped = 0
        companies_errors = 0
        total_cost = 0.0
        
        try:
            with open(csv_path, 'r', encoding='utf-8') as f:
                # Read all lines to find the actual header
                lines = f.readlines()
                
                # Find the line that contains "Company Name" - this should be our header
                header_line_idx = None
                for i, line in enumerate(lines):
                    if 'Company Name' in line and 'NIF Code' in line:
                        header_line_idx = i
                        break
                
                if header_line_idx is None:
                    raise ValueError("Could not find header line with 'Company Name' and 'NIF Code'")
                
                # Use the found header line
                header_line = lines[header_line_idx].strip()
                reader = csv.DictReader([header_line] + lines[header_line_idx + 1:])
                
                for i, row in enumerate(reader):
                    if limit and i >= limit:
                        break
                    
                    try:
                        # Extract basic info
                        company_name = row.get('Company Name', '').strip()
                        if not company_name:
                            logger.info("company_no_name_skipped", row=i)
                            companies_skipped += 1
                            continue
                        
                        logger.info("processing_company", 
                                  row=i, 
                                  name=company_name[:50])
                        
                        nif = row.get('NIF Code', '').strip()
                        employees = None
                        try:
                            if row.get('Latest number of employees'):
                                employees = int(float(row['Latest number of employees']))
                        except:
                            pass
                        
                        turnover = None
                        try:
                            if row.get('Operating revenue / turnover\nth EUR\nLast avail. yr'):
                                turnover = float(row['Operating revenue / turnover\nth EUR\nLast avail. yr'])
                        except:
                            pass
                        
                        # Parse CAE codes
                        cae_primary = row.get('CAE Rev.3 Primary Code', '').strip()
                        cae_secondary = row.get('CAE Rev.3 Secondary Code(s)', '').strip()
                        cae_codes = []
                        
                        if cae_primary:
                            cae_codes.extend(parse_cae_codes(cae_primary))
                        if cae_secondary:
                            cae_codes.extend(parse_cae_codes(cae_secondary))
                        
                        # Remove duplicates
                        cae_codes = list(set(cae_codes))
                        
                        # Determine company size
                        company_size = determine_company_size(employees, turnover)
                        
                        # Extract location
                        postal_code = row.get('Postal Code', '').strip()
                        district = row.get('DM\nFull name', '').strip()  # This might be district
                        location = extract_location(postal_code, district)
                        
                        # Create company object
                        company = Company(
                            company_id=f"nif_{nif}" if nif else f"name_{hash(company_name) % 1000000}",
                            name=company_name,
                            cae_codes=cae_codes,
                            size=company_size,
                            district=location['district'],
                            county=location['county'],
                            parish=location['parish'],
                            website=row.get('Web site', '').strip() or None,
                            raw={
                                'nif': nif,
                                'employees': employees,
                                'turnover': turnover,
                                'description': row.get('Native trade description', '').strip() or 
                                              row.get('English trade description', '').strip()
                            }
                        )
                        
                        # Check for duplicates by name and district
                        existing = db.query(Company).filter(
                            Company.name == company_name,
                            Company.district == location['district']
                        ).first()
                        
                        if existing:
                            logger.info("company_duplicate_skipped", 
                                      name=company_name, 
                                      district=location['district'])
                            companies_skipped += 1
                            continue
                        
                        # Save company
                        db.add(company)
                        db.flush()  # Get the ID
                        
                        # Generate embedding
                        document_id = f"company_{company.company_id}"
                        embedding_result = embedding_service.generate_company_embedding(
                            db, company, force_refresh=True
                        )
                        
                        if embedding_result:
                            # Get cost for this company from the embedding result
                            cost = embedding_result.cost_eur if hasattr(embedding_result, 'cost_eur') else 0.0
                            total_cost += cost
                        
                        companies_loaded += 1
                        
                        if companies_loaded % 100 == 0:
                            logger.info("companies_progress", 
                                      loaded=companies_loaded, 
                                      skipped=companies_skipped,
                                      errors=companies_errors)
                            db.commit()
                    
                    except Exception as e:
                        companies_errors += 1
                        logger.error("company_processing_error", 
                                   row=i, 
                                   error=str(e),
                                   exc_info=True)
                        continue
                
                # Final commit
                db.commit()
                
                logger.info("companies_loading_complete",
                          total_loaded=companies_loaded,
                          total_skipped=companies_skipped,
                          total_errors=companies_errors,
                          total_cost_eur=total_cost)
                
                return {
                    'total': companies_loaded + companies_skipped + companies_errors,
                    'loaded': companies_loaded,
                    'skipped': companies_skipped,
                    'errors': companies_errors,
                    'total_cost_eur': total_cost
                }
                
        except Exception as e:
            logger.error("csv_loading_failed", error=str(e), exc_info=True)
            db.rollback()
            raise


def main():
    """Main function."""
    parser = argparse.ArgumentParser(description="Load companies from CSV")
    parser.add_argument(
        "--csv-path",
        type=str,
        default="/app/companies_sample.csv",
        help="Path to companies CSV file"
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Maximum number of companies to process"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force reload even if companies exist"
    )
    
    args = parser.parse_args()
    
    print("\n" + "="*60)
    print("LOADING COMPANIES FROM CSV")
    print("="*60 + "\n")
    
    try:
        stats = load_companies_from_csv(
            csv_path=args.csv_path,
            limit=args.limit,
            force=args.force
        )
        
        print(f"\n✅ Company Loading Complete!")
        print(f"   Total processed: {stats['total']}")
        print(f"   Loaded: {stats['loaded']}")
        print(f"   Skipped: {stats['skipped']}")
        print(f"   Errors: {stats['errors']}")
        print(f"   Cost: €{stats['total_cost_eur']:.4f}")
        
    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted by user")
        sys.exit(1)
    
    except Exception as e:
        print(f"\n\n❌ Error: {e}")
        logger.error("script_failed", error=str(e), exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
