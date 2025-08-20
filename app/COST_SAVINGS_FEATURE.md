# Cost Savings Feature for Relationship Classification

## Overview

This feature adds intelligent filtering to reduce AI costs by checking for existing relationships before sending claim pairs to the LLM for classification.

## Problem

The original system would send all similar claim pairs to the LLM for classification, even if relationships already existed between those claims. This resulted in unnecessary AI costs for processing pairs that had already been analyzed.

## Solution

Added pre-processing checks that examine the database for existing relationships before sending pairs to the LLM.

## Key Methods

### 1. `_should_process_claim_pair()`
- **Purpose**: Determines if a claim pair should be sent to the LLM
- **Returns**: Boolean indicating whether to process the pair
- **Logic**: 
  - Returns `False` if any relationship already exists (conservative approach)
  - Returns `True` if no relationships exist
- **Implementation**: Uses the consolidated `sql_store.check_claim_relationship()` function

### 2. `_filter_and_store_relationships()`
- **Purpose**: Filters out neutral relationships and stores the rest
- **Logic**: Only neutral relationships are filtered out during storage (duplicates are already filtered during batch formation)
- **Optimization**: No duplicate checking needed since it's done during batch formation

## How It Works

1. **Pre-Processing Check**: Before sending a claim pair to the LLM, the system checks the database for existing relationships
2. **Filtering Decision**: If relationships already exist, the pair is skipped
3. **Storage**: Only neutral relationships are filtered out during storage (duplicates are already filtered during batch formation)
4. **Cost Tracking**: Statistics are tracked to show cost savings
5. **Logging**: Detailed logs show how many pairs were skipped vs. processed

## Cost Savings Statistics

The system now tracks and reports:
- **Total pairs considered**: All claim pairs found by similarity search
- **Pairs skipped**: Pairs that already had relationships (cost savings)
- **Pairs processed**: Pairs actually sent to the LLM
- **Cost savings percentage**: Percentage of pairs that didn't need LLM processing

## Example Output

```
Canonical claims processing complete:
  - Total pairs considered: 150
  - Pairs skipped (cost savings): 45
  - Pairs processed: 105
  - Cost savings: 30.0%
  - Relationships created: 23
```

## Configuration

The feature is automatically enabled and uses the existing relationship types:
- `supports`
- `opposes` 
- `neutral`

## Benefits

1. **Reduced AI Costs**: Skip processing of already-analyzed claim pairs
2. **Faster Processing**: Less time spent on redundant LLM calls
3. **Better Resource Utilization**: Focus AI processing on new relationships
4. **Transparency**: Clear reporting of cost savings achieved

## Future Enhancements

1. **Granular Processing**: Process only for missing relationship types
2. **Confidence-based Filtering**: Re-process low-confidence relationships
3. **Temporal Filtering**: Re-process old relationships after a certain time
4. **Batch Optimization**: Optimize batch sizes based on cost savings

## Usage

The feature is automatically applied when running the relationship classifier:

```python
from routines.claim_relationship_classifier import ClaimRelationshipClassifier

# Run classification with cost savings
stats = ClaimRelationshipClassifier.classify_claim_relationships("both", force_reprocess=False)
```

The system will automatically skip pairs that already have relationships and report the cost savings achieved.
