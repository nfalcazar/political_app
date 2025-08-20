# Duplicate Check Optimization

## Overview

This document describes the optimization to remove redundant duplicate checking during relationship storage, since duplicates are already filtered out during batch formation.

## Problem

The system was performing duplicate checks in two places:
1. **During batch formation**: `_should_process_claim_pair()` checks for existing relationships before sending pairs to the LLM
2. **During storage**: `_filter_and_store_relationships()` checks for existing relationships before storing edges

This resulted in:
- Redundant database queries
- Unnecessary processing overhead
- Code duplication

## Solution

Removed the duplicate check from the storage phase since it's already handled during batch formation.

## Changes Made

### Before:
```python
def _filter_and_store_relationships(cls, sql_store, relationships):
    for relationship in relationships:
        # Skip neutral relationships
        if relationship['relationship_type'] == 'neutral':
            continue
        
        # REDUNDANT: Check for existing relationships
        if sql_store.check_claim_relationship(...):
            continue
        
        # Store relationship
        sql_store.create_edge(...)
```

### After:
```python
def _filter_and_store_relationships(cls, sql_store, relationships):
    for relationship in relationships:
        # Skip neutral relationships only
        if relationship['relationship_type'] == 'neutral':
            continue
        
        # Store relationship (no duplicate check needed - done during batch formation)
        sql_store.create_edge(...)
```

## Why This Works

1. **Batch Formation Filtering**: `_should_process_claim_pair()` filters out pairs that have existing relationships
2. **Intra-Batch Deduplication**: `_should_process_claim_pair()` with `seen_relationships` prevents duplicates within the same batch during formation
3. **LLM Processing**: Only unique pairs without existing relationships are sent to the LLM
4. **Storage**: All relationships returned by the LLM are new and don't need database duplicate checking

## Benefits

1. **Reduced Database Queries**: Eliminates redundant relationship checks
2. **Improved Performance**: Faster storage processing
3. **Cleaner Code**: Removes unnecessary duplicate logic
4. **Better Resource Utilization**: Less database load
5. **Cost Savings**: Prevents unnecessary LLM API calls for duplicate relationships
6. **Pre-LLM Filtering**: Filters duplicates during batch formation, not after LLM processing

## Verification

The optimization is safe because:
- All relationship pairs are pre-filtered during batch formation
- Intra-batch deduplication prevents duplicates within the same batch during formation
- The LLM only processes unique pairs that don't have existing relationships
- Therefore, all relationships returned by the LLM are guaranteed to be new and unique

## Impact

- **Performance**: Faster storage processing
- **Database Load**: Reduced number of queries
- **Code Complexity**: Simplified storage logic
- **Functionality**: No change in behavior - same results with better performance
