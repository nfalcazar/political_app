#!/usr/bin/env python3
"""
Debug script to investigate edge and source relationships.
"""

import sys
from pathlib import Path

# Add the app directory to the path so we can import our modules
sys.path.insert(0, str(Path(__file__).parent))

from database.sql_api import SqlStore


def debug_claim_sources():
    """Debug source relationships for a specific claim."""
    
    print("🔍 Debugging Claim-Source Relationships")
    print("=" * 50)
    
    sql_store = SqlStore()
    
    # Test with one of the claims we found
    claim_id = "fe13573a-7d60-11f0-83cb-31274625043e"
    
    print(f"Testing claim ID: {claim_id}")
    
    # 1. Check if the claim exists
    print("\n1. Checking if claim exists...")
    claim_data = sql_store.get_data_by_field('canon_claims', 'id', claim_id)
    if claim_data:
        print(f"✅ Claim found: {claim_data[0].get('content', 'No content')[:100]}...")
    else:
        print("❌ Claim not found in canon_claims table")
        return
    
    # 2. Get all edges for this claim
    print("\n2. Getting all edges for this claim...")
    edges = sql_store.get_edges_by_node('canonical_claim', claim_id)
    print(f"Found {len(edges)} edges")
    
    for i, edge in enumerate(edges, 1):
        print(f"   Edge {i}:")
        print(f"     ID: {edge.get('id')}")
        print(f"     Source: {edge.get('src_type')}:{edge.get('src_id')}")
        print(f"     Destination: {edge.get('dest_type')}:{edge.get('dest_id')}")
        print(f"     Relationship: {edge.get('relationship_type')}")
        print(f"     Direction: {edge.get('direction')}")
    
    # 3. Check if there are any sources in the database
    print("\n3. Checking sources table...")
    try:
        # Try to get a few sources to see if the table has data
        from sqlalchemy import text
        with sql_store.engine.connect() as connection:
            result = connection.execute(text("SELECT COUNT(*) FROM sources"))
            count = result.fetchone()[0]
            print(f"Total sources in database: {count}")
            
            if count > 0:
                result = connection.execute(text("SELECT id, description FROM sources LIMIT 3"))
                sources = result.fetchall()
                print("Sample sources:")
                for source in sources:
                    print(f"   {source[0]}: {source[1][:50]}...")
    except Exception as e:
        print(f"❌ Error checking sources: {e}")
    
    # 4. Check edges table structure
    print("\n4. Checking edges table...")
    try:
        from sqlalchemy import text
        with sql_store.engine.connect() as connection:
            result = connection.execute(text("SELECT COUNT(*) FROM edges"))
            count = result.fetchone()[0]
            print(f"Total edges in database: {count}")
            
            if count > 0:
                result = connection.execute(text("SELECT src_type, dest_type, relationship_type FROM edges LIMIT 5"))
                edges_sample = result.fetchall()
                print("Sample edges:")
                for edge in edges_sample:
                    print(f"   {edge[0]} -> {edge[1]} ({edge[2]})")
    except Exception as e:
        print(f"❌ Error checking edges: {e}")


def debug_all_edges():
    """Debug all edges in the database."""
    
    print("\n🔍 Debugging All Edges")
    print("=" * 30)
    
    sql_store = SqlStore()
    
    try:
        from sqlalchemy import text
        with sql_store.engine.connect() as connection:
            # Get all edges
            result = connection.execute(text("""
                SELECT e.id, e.src_type, e.src_id, e.dest_type, e.dest_id, e.relationship_type,
                       c.content as claim_content,
                       s.description as source_description
                FROM edges e
                LEFT JOIN canon_claims c ON (e.src_type = 'canonical_claim' AND e.src_id = c.id) 
                    OR (e.dest_type = 'canonical_claim' AND e.dest_id = c.id)
                LEFT JOIN sources s ON (e.src_type = 'source' AND e.src_id = s.id) 
                    OR (e.dest_type = 'source' AND e.dest_id = s.id)
                ORDER BY e.relationship_type
            """))
            
            edges = result.fetchall()
            print(f"Found {len(edges)} total edges")
            
            for edge in edges[:10]:  # Show first 10
                print(f"\nEdge: {edge[0]}")
                print(f"  {edge[1]}:{edge[2]} -> {edge[3]}:{edge[4]} ({edge[5]})")
                if edge[6]:  # claim content
                    print(f"  Claim: {edge[6][:50]}...")
                if edge[7]:  # source description
                    print(f"  Source: {edge[7][:50]}...")
                    
    except Exception as e:
        print(f"❌ Error: {e}")


if __name__ == "__main__":
    debug_claim_sources()
    debug_all_edges()
