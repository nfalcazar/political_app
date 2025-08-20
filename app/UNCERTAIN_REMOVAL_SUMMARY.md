# Removal of "Uncertain" Relationship Type

## Summary

The "uncertain" relationship type has been removed from the classification system. Cases that were previously classified as "uncertain" are now classified as "opposes" to simplify the system and make it cleaner.

## Changes Made

### 1. System Prompt (`app/prompts/relationship_classification_sys.txt`)
- **Removed**: Separate "UNCERTAIN" classification section
- **Updated**: "OPPOSES" section to include cases that were previously "uncertain":
  - Claims that need more information, context, or show the relationship is unknowable
  - Claims about different aspects of the same topic that don't support each other
  - Claims that are too vague to classify as supporting
- **Updated**: JSON output format to only include "supports", "opposes", "neutral"

### 2. Configuration (`app/routines/relationship_config.py`)
- **Updated**: `SUPPORTED_RELATIONSHIP_TYPES` to remove "uncertain"
- **New**: `["supports", "opposes", "neutral"]`

### 3. Database Queries (`app/database/sql_api.py`)
- **Updated**: All SQL queries to remove "uncertain" from relationship type checks
- **Updated**: Three instances of relationship type filtering

### 4. Relationship Classifier (`app/routines/claim_relationship_classifier.py`)
- **Updated**: User prompts to remove "uncertain" from relationship type options
- **Updated**: SQL queries in `_is_claim_processed()` method

## Rationale

The "uncertain" category was originally meant for claims that:
- Need more information or context
- Show the relationship is unknowable
- Are too vague to classify

However, these cases are better classified as "opposes" because:
1. They don't support the original claim
2. They introduce doubt or uncertainty about the claim
3. They effectively weaken or contradict the claim's certainty
4. It simplifies the classification system to three clear categories

## Benefits

1. **Simpler Classification**: Only three relationship types instead of four
2. **Clearer Logic**: Claims that don't support are either neutral (unrelated) or oppose (related but not supporting)
3. **Better Graph Quality**: Fewer ambiguous relationships in the knowledge graph
4. **Easier LLM Training**: Simpler prompt with fewer options

## Impact

- Existing "uncertain" relationships in the database will continue to work
- New classifications will use the three-type system
- The system is now cleaner and more intuitive
