# Relationship Checking Consolidation

## Overview

This document describes the consolidation of relationship checking logic into a single `check_claim_relationship` function in the SQL API to reduce code duplication and improve maintainability.

## Problem

The system had multiple scattered functions for checking relationships:
- `relationship_exists_bidirectional()` in SqlStore
- `_relationship_exists_with_same_type()` in ClaimRelationshipClassifier
- `_get_existing_relationship_types()` in ClaimRelationshipClassifier
- `_is_claim_processed()` in ClaimRelationshipClassifier

This led to:
- Code duplication
- Inconsistent query patterns
- Difficult maintenance
- Multiple places to update when relationship logic changes

## Solution

Created a single consolidated `check_claim_relationship()` function in `SqlStore` that handles all relationship checking scenarios.

## New Consolidated Function

### `check_claim_relationship(claim_id, claim_type, relationship_type=None, other_claim_id=None)`

This function provides flexible relationship checking based on the parameters provided:

#### Usage Patterns:

1. **Check all relationships for a claim:**
   ```python
   relationships = sql_store.check_claim_relationship(claim_id, claim_type)
   # Returns: List[str] - e.g., ["supports", "opposes"]
   ```

2. **Check if claim has specific relationship type:**
   ```python
   has_supports = sql_store.check_claim_relationship(claim_id, claim_type, "supports")
   # Returns: bool - True if claim has any "supports" relationships
   ```

3. **Check relationships between two claims:**
   ```python
   relationship_types = sql_store.check_claim_relationship(claim_id, claim_type, other_claim_id=other_claim_id)
   # Returns: List[str] - e.g., ["supports"] or []
   ```

4. **Check specific relationship type between two claims:**
   ```python
   has_relationship = sql_store.check_claim_relationship(claim_id, claim_type, "supports", other_claim_id)
   # Returns: bool - True if specific relationship exists
   ```

## Removed Functions

The following functions were removed from `ClaimRelationshipClassifier`:
- `_relationship_exists_with_same_type()`
- `_get_existing_relationship_types()`

## Updated Functions

### `_should_process_claim_pair()`
- Now uses `sql_store.check_claim_relationship()` instead of `_get_existing_relationship_types()`
- Simplified logic with fewer database queries

### `_is_claim_processed()`
- Now uses `sql_store.check_claim_relationship()` instead of direct SQL query
- Cleaner implementation with better error handling

### `_filter_and_store_relationships()`
- Now uses `sql_store.check_claim_relationship()` for duplicate checking
- More consistent with the rest of the codebase

## Benefits

1. **Reduced Code Duplication**: Single function handles all relationship checking scenarios
2. **Improved Maintainability**: Changes to relationship logic only need to be made in one place
3. **Consistent API**: All relationship checking uses the same function with different parameters
4. **Better Performance**: Optimized queries and reduced database connections
5. **Cleaner Code**: Removed redundant methods and simplified existing ones

## Migration Guide

### Before:
```python
# Check if relationship exists
exists = sql_store.relationship_exists_bidirectional(claim_a, claim_b, claim_type)

# Get existing relationship types
types = cls._get_existing_relationship_types(sql_store, claim_a, claim_b, claim_type)

# Check specific relationship type
has_type = cls._relationship_exists_with_same_type(sql_store, claim_a, claim_b, claim_type, "supports")
```

### After:
```python
# Check if any relationship exists
exists = bool(sql_store.check_claim_relationship(claim_a, claim_type, other_claim_id=claim_b))

# Get existing relationship types
types = sql_store.check_claim_relationship(claim_a, claim_type, other_claim_id=claim_b)

# Check specific relationship type
has_type = sql_store.check_claim_relationship(claim_a, claim_type, "supports", claim_b)
```

## Testing

A test script `test_consolidated_relationship.py` has been created to verify all usage patterns work correctly.

## Future Enhancements

The consolidated function provides a foundation for:
1. **Caching**: Can add caching to reduce database queries
2. **Batch Operations**: Can extend to handle multiple claims at once
3. **Advanced Filtering**: Can add more sophisticated filtering options
4. **Performance Monitoring**: Can add query performance tracking
