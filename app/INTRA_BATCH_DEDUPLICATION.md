# Intra-Batch Deduplication Fix

## Problem Identified

You correctly identified that there was a potential issue where duplicate relationships could be created within the same batch, even after removing the database duplicate check. This could happen because:

1. **No intra-batch filtering**: The system didn't check for duplicates within the relationships list from a single batch
2. **LLM could return duplicates**: The LLM might return the same relationship type for the same claim pair multiple times
3. **All relationships stored together**: All relationships from a batch were stored at once without internal deduplication

## Example Scenario

```python
# LLM returns these relationships for a batch:
[
    {"src_id": "A", "dest_id": "B", "relationship_type": "supports"},
    {"src_id": "A", "dest_id": "B", "relationship_type": "supports"},  # Exact duplicate!
    {"src_id": "B", "dest_id": "A", "relationship_type": "supports"},  # Bidirectional duplicate!
    {"src_id": "A", "dest_id": "C", "relationship_type": "opposes"}
]

# Without intra-batch deduplication, all three "supports" relationships would be stored
# With bidirectional deduplication, only the first one is stored
```

## Solution Implemented

Added bidirectional intra-batch deduplication during batch formation in `_process_claim` methods:

```python
def _should_process_claim_pair(cls, sql_store, src_id, dest_id, claim_type, seen_relationships=None):
    # Check database for existing relationships
    existing_types = sql_store.check_claim_relationship(src_id, claim_type, other_claim_id=dest_id)
    if existing_types:
        return False
    
    # Check for intra-batch duplicates if seen_relationships is provided
    if seen_relationships is not None:
        relationship_key_forward = (src_id, dest_id)
        relationship_key_reverse = (dest_id, src_id)
        
        if relationship_key_forward in seen_relationships or relationship_key_reverse in seen_relationships:
            return False
    
    return True

# In _process_claim methods:
seen_relationships = set()
for similar_claim in similar_claims:
    if cls._should_process_claim_pair(sql_store, claim['id'], similar_claim['id'], 'claim', seen_relationships):
        filtered_similar_claims.append(similar_claim)
        # Add to seen relationships to prevent future duplicates
        seen_relationships.add((claim['id'], similar_claim['id']))
        seen_relationships.add((similar_claim['id'], claim['id']))
```

## Key Features

1. **Bidirectional Key Generation**: Creates keys for both directions `(src_id, dest_id)` and `(dest_id, src_id)`
2. **Bidirectional Duplicate Detection**: Checks for duplicates in either direction
3. **Pre-LLM Filtering**: Prevents unnecessary LLM API calls by filtering duplicates during batch formation
4. **Set-based Tracking**: Uses a set to efficiently track seen relationships within the batch
5. **Logging**: Logs when duplicates are found and filtered out
6. **Cost Savings**: Avoids LLM API calls for duplicate relationships

## Benefits

1. **Prevents Duplicate Edges**: Ensures no duplicate relationships are stored in the database
2. **Bidirectional Protection**: Prevents duplicates regardless of which claim is src vs dest
3. **Cost Savings**: Avoids unnecessary LLM API calls for duplicate relationships
4. **Pre-LLM Filtering**: Filters duplicates before sending to LLM, not after
5. **Maintains Data Integrity**: Guarantees unique relationships
6. **Efficient Processing**: Uses set-based lookup for O(1) duplicate checking
7. **Transparency**: Logs and reports duplicate filtering statistics

## Complete Protection Now

The system now has comprehensive duplicate protection at multiple levels:

1. **Pre-Batch**: `_should_process_claim_pair()` filters out pairs with existing database relationships
2. **Intra-Batch**: `_should_process_claim_pair()` with `seen_relationships` prevents duplicates within the same batch during formation
3. **Database Level**: Database constraints prevent duplicate edges (if configured)

## Testing

The fix ensures that duplicate relationships are filtered out during batch formation, preventing unnecessary LLM API calls.

### Example Test Cases:

1. **Exact Duplicate**: `A -> B` followed by `A -> B` → Only first sent to LLM
2. **Bidirectional Duplicate**: `A -> B` followed by `B -> A` → Only first sent to LLM  
3. **Different Claims**: `A -> B` and `A -> C` → Both sent to LLM (different claims)
4. **Database Existing**: `A -> B` where relationship already exists → Not sent to LLM

## Impact

- **Data Quality**: Guaranteed unique relationships in the database
- **Cost Savings**: Avoids unnecessary LLM API calls for duplicate relationships
- **Performance**: Minimal overhead for duplicate checking during batch formation
- **Reliability**: Robust protection against various sources of duplicates
- **Debugging**: Clear logging when duplicates are detected and filtered
