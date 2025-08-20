# Relationship Classification Improvements

## Overview

This document describes the improvements made to the claim relationship classification system to address issues with duplicate edges and add support for neutral relationships.

## Key Improvements

### 1. Neutral Relationship Support

**Problem**: The system only supported "supports", "opposes", and "uncertain" relationships, but some claim pairs may not have meaningful relationships.

**Solution**: Added support for "neutral" relationships that result in no edge creation, and removed "uncertain" by lumping those cases with "opposes".

**Changes Made**:
- Updated system prompt (`app/prompts/relationship_classification_sys.txt`) to include "neutral" as a relationship type and expanded "opposes" to include uncertain cases
- Updated relationship configuration (`app/routines/relationship_config.py`) to include "neutral" and remove "uncertain" from supported types
- Updated SQL queries in `app/database/sql_api.py` to include "neutral" and remove "uncertain" from relationship checks
- Modified relationship storage logic to filter out neutral relationships before creating edges

### 2. Bidirectional Relationship Checking

**Problem**: The system was creating duplicate edges when both ClaimA→ClaimB and ClaimB→ClaimA were processed, even if they had the same relationship type.

**Solution**: Added comprehensive bidirectional relationship checking to prevent duplicate edges.

**Changes Made**:
- Enhanced `relationship_exists_bidirectional()` method in `SqlStore` to check for any relationship type
- Added `_relationship_exists_with_same_type()` method to check for specific relationship types in both directions
- Updated relationship filtering logic to skip relationships that already exist with the same type

### 3. Asymmetric Relationship Support

**Problem**: The system didn't account for cases where ClaimA→ClaimB and ClaimB→ClaimA could have different relationship types.

**Solution**: The improved system now allows for asymmetric relationships while preventing exact duplicates.

**Example**:
- ClaimA supports ClaimB (creates edge A→B with "supports")
- ClaimB opposes ClaimA (creates edge B→A with "opposes") 
- Claims that need more context or are unknowable are classified as "opposes"
- Both relationships can coexist as they represent different directions and types

## Technical Implementation

### New Methods Added

1. **`_relationship_exists_with_same_type()`**: Checks if a specific relationship type already exists between two claims in either direction
2. **`_filter_and_store_relationships()`**: Enhanced relationship storage that filters out neutral relationships and duplicates

### Updated Methods

1. **`_store_relationships()`**: Now delegates to the new filtering method
2. **`_is_claim_processed()`**: Updated to include neutral relationships in processing checks
3. **User prompts**: Updated to include "neutral" as a relationship option

### Database Changes

- All SQL queries now include "neutral" in relationship type checks
- Bidirectional relationship checking is more comprehensive

## Benefits

1. **Reduced Duplicate Edges**: Prevents creation of identical relationships in both directions
2. **Better Relationship Modeling**: Allows for asymmetric relationships where appropriate
3. **Cleaner Graph**: Neutral relationships don't clutter the knowledge graph
4. **Improved Performance**: Fewer unnecessary edge creations and database operations

## Testing

A test script (`app/test_relationship_improvements.py`) has been created to verify:
- Neutral relationships are properly filtered out
- Duplicate relationships are not created
- Bidirectional checking works correctly
- Asymmetric relationships are allowed

## Usage

The improvements are automatically applied when running the relationship classifier:

```python
from routines.claim_relationship_classifier import ClaimRelationshipClassifier

# Run classification with improvements
stats = ClaimRelationshipClassifier.classify_claim_relationships("both", force_reprocess=False)
```

## Configuration

The system uses the updated configuration in `app/routines/relationship_config.py`:

```python
SUPPORTED_RELATIONSHIP_TYPES = ["supports", "opposes", "neutral"]
```

## Future Enhancements

1. **Confidence-based Filtering**: Consider filtering out low-confidence relationships
2. **Relationship Strength**: Add support for relationship strength/weight attributes
3. **Temporal Relationships**: Consider time-based relationship evolution
4. **Batch Processing**: Optimize for large-scale relationship classification
