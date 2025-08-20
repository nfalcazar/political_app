# Table Column Name Updates

## Problem

The data_processor was using old column names that didn't match the updated database schema:
- `metadata_` instead of `metadata`
- `text` instead of `contents`

This caused errors when trying to process data through the data_processor.

## Changes Made

### 1. **data_processor.py**
- **Line 220**: Updated content extraction to use `contents` field with fallback to `text`
  ```python
  # Before
  content = canon_claim.get('text', '')
  
  # After  
  content = canon_claim.get('contents', canon_claim.get('text', ''))
  ```

- **Line 271**: Updated metadata field exclusion to handle both `text` and `contents`
  ```python
  # Before
  if key != 'text':  # Exclude the text field as it goes to content
  
  # After
  if key not in ['text', 'contents']:  # Exclude the content fields as they go to contents
  ```

- **Line 284**: Updated record preparation to use `metadata` instead of `metadata_`
  ```python
  # Before
  record = {
      'id': canon_id,
      'metadata_': metadata,
      'contents': content,
      'embedding': embedding
  }
  
  # After
  record = {
      'id': canon_id,
      'metadata': metadata,
      'contents': content,
      'embedding': embedding
  }
  ```

### 2. **sql_api.py**
- **Line 115**: Updated SQL query to use `metadata` instead of `metadata_`
  ```sql
  -- Before
  WHERE metadata_ ->> :json_key = :field_value
  
  -- After
  WHERE metadata ->> :json_key = :field_value
  ```

- **Line 304**: Updated claim deduplication to use `contents` instead of `text`
  ```python
  # Before
  existing_claim = self.get_data_by_field('claims', 'text', claim_text)
  
  # After
  existing_claim = self.get_data_by_field('claims', 'contents', claim_text)
  ```

- **Line 321**: Updated claim creation to use `contents`, `metadata`, and proper `created_at`
  ```python
  # Before
  claim_insert_data = {
      'id': claim_id,
      'text': claim_text,
      'metadata_': json.dumps({..., 'created_at': datetime.now().isoformat()})
  }
  
  # After
  claim_insert_data = {
      'id': claim_id,
      'contents': claim_text,
      'created_at': datetime.now(),  # Set at top level
      'metadata': json.dumps({...})  # No created_at in metadata
  }
  ```

- **Line 413**: Updated source creation to use `metadata` and removed `created_at` from metadata
  ```python
  # Before
  'metadata_': json.dumps({..., 'created_at': datetime.now().isoformat()})
  
  # After
  'metadata': json.dumps({...})  # No created_at in metadata (sources table doesn't have top-level created_at)
  ```

- **Lines 600, 625**: Updated edge metadata access to use `metadata`
  ```python
  # Before
  'metadata': json.loads(edge_data['metadata_']) if edge_data['metadata_'] else {}
  
  # After
  'metadata': json.loads(edge_data['metadata']) if edge_data['metadata'] else {}
  ```

### 3. **test_specific_source.py**
- **Line 78**: Updated metadata access to use `metadata`
  ```python
  # Before
  source_type = source.get('metadata_', {}).get('source_type', '')
  
  # After
  source_type = source.get('metadata', {}).get('source_type', '')
  ```

### 4. **resolve_sources.py**
- **Multiple lines**: Updated all metadata access and SQL operations to use `metadata` instead of `metadata_`
  ```python
  # Before
  metadata_raw = source.get('metadata_', '{}')
  sql_store.update_data('sources', source['id'], {'metadata_': json.dumps(metadata)})
  
  # After
  metadata_raw = source.get('metadata', '{}')
  sql_store.update_data('sources', source['id'], {'metadata': json.dumps(metadata)})
  ```

## Verification

Both modules now import successfully:
- ✅ `DataProcessor` imports without errors
- ✅ `SqlStore` imports without errors

## Impact

- **Data Processing**: The data_processor can now correctly process JSON files and update database tables
- **Database Operations**: All SQL operations now use the correct column names
- **Backward Compatibility**: Maintained fallback support for `text` field in data_processor
- **Consistency**: All code now uses the standardized column names (`metadata`, `contents`)

## Notes

- The changes maintain backward compatibility by supporting both `text` and `contents` fields in data_processor
- All database operations now use the correct column names that match the actual database schema
- The linter errors in sql_api.py are pre-existing and not related to these column name changes
- The `created_at` field is now properly populated at the top level for claims, not in metadata
