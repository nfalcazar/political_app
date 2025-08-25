# Political Claims Search CLI

This CLI tool allows you to search the political claims database using vector similarity search. It searches the `canon_claims` table and returns claims that meet a specified similarity threshold.

## Features

- **Vector Similarity Search**: Uses embeddings to find semantically similar claims
- **Configurable Threshold**: Set similarity threshold (0.0-1.0) to filter results
- **Source Information**: Optionally include source information for each claim
- **Interactive Mode**: Run interactive sessions for multiple searches
- **Command Line Interface**: Use command line arguments for automation

## Usage

### Interactive Mode (Recommended for exploration)

```bash
cd app
python search_cli.py --interactive
```

This will start an interactive session where you can:
- Enter claims to search for
- Set similarity thresholds for each search
- Choose how many results to return
- Decide whether to include source information

### Command Line Mode

```bash
# Basic search
python search_cli.py --query "immigration policy changes"

# Search with custom threshold
python search_cli.py --query "tax reform" --threshold 0.8

# Limit results and exclude sources
python search_cli.py --query "healthcare policy" --limit 5 --no-sources

# Verbose logging
python search_cli.py --query "climate change" --verbose
```

### Command Line Options

- `--query, -q`: Claim text to search for
- `--threshold, -t`: Similarity threshold (0.0-1.0, default: 0.7)
- `--limit, -l`: Maximum number of results (default: 10)
- `--no-sources`: Exclude source information from results
- `--interactive, -i`: Run in interactive mode
- `--verbose, -v`: Enable verbose logging

## Understanding Similarity Scores

- **1.0**: Exact semantic match
- **0.8-0.9**: Very similar claims
- **0.7-0.8**: Moderately similar claims
- **0.5-0.7**: Somewhat related claims
- **< 0.5**: Weakly related or unrelated claims

## Example Output

```
🔍 Searching for: 'immigration policy changes'
📊 Similarity threshold: 0.7
📋 Max results: 10
⏳ Searching...

Found 3 claims with similarity >= 0.7

📋 Results (3 found):
================================================================================

1. Claim ID: canon_12345
   Similarity: 0.8542
   Text: The Biden administration implemented new immigration policies that affect border processing
   Category: immigration
   Sources (2):
     1. Department of Homeland Security Press Release
        Type: official_release_or_speech
        Publisher: DHS
     2. White House Executive Order
        Type: official_document
        Publisher: White House

2. Claim ID: canon_67890
   Similarity: 0.7234
   Text: Recent changes to immigration enforcement procedures at the southern border
   Category: immigration
   Sources (1):
     1. Border Patrol Policy Update
        Type: official_document
        Publisher: CBP

================================================================================
```

## Tips for Effective Searching

1. **Use Natural Language**: Write claims as you would naturally express them
2. **Start with Lower Thresholds**: Begin with 0.6-0.7 and adjust based on results
3. **Include Key Terms**: Use specific policy names, dates, or entities when relevant
4. **Try Different Phrasings**: If no results, try rephrasing your query
5. **Use Interactive Mode**: Great for exploring and refining searches

## Technical Details

- Uses OpenAI embeddings for semantic similarity
- Searches the `canon_claims` table in your TimescaleDB
- Connects to sources via graph edges in the database
- Supports metadata filtering and time-based queries (via the underlying VectorStore)

## Troubleshooting

- **No Results**: Try lowering the similarity threshold
- **Too Many Results**: Increase the similarity threshold
- **Connection Errors**: Ensure your database is running and environment variables are set
- **Import Errors**: Make sure you're running from the `app` directory
- **API Key Errors**: Make sure `OPENAI_API_KEY` is set in your `.env` file
- **Database Connection**: Ensure `SQL_URL` and `TIMESCALE_SERVICE_URL` are set in your `.env` file

## Environment Variables

Make sure your `.env` file contains the following variables:

```bash
# Database URLs
SQL_URL=postgresql://username:password@host:port/database
TIMESCALE_SERVICE_URL=postgres://username:password@host:port/database

# OpenAI API Key (for embeddings)
OPENAI_API_KEY=your_openai_api_key_here

# Project root
PROJ_ROOT=/path/to/your/project
```
