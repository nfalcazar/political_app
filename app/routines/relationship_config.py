"""
Configuration settings for the Claim Relationship Classifier.
"""

# Vector similarity settings
SIMILARITY_THRESHOLD = 0.75  # Minimum similarity to consider claims related
MAX_SIMILAR_CLAIMS = 10      # Maximum similar claims to analyze per claim
BATCH_SIZE = 5               # Number of claim pairs per LLM call

# Processing settings
FORCE_REPROCESS = False      # Whether to reprocess existing relationships
PROCESS_CANON_CLAIMS = True  # Whether to process canonical claims
PROCESS_REGULAR_CLAIMS = True # Whether to process regular claims

# Scheduling settings (for BackgroundScheduler)
RELATIONSHIP_CHECK_INTERVAL_HOURS = 2  # How often to run relationship classification
DAILY_REPROCESS = True                 # Whether to do daily full reprocessing

# LLM settings
LLM_PROVIDER = "openai"      # "openai" or "deepseek"
LLM_MODEL = "gpt-4o-mini"    # Model to use for classification

# Logging settings
LOG_LEVEL = "INFO"
LOG_PROGRESS_INTERVAL = 10   # Log progress every N claims

# Performance settings
RATE_LIMIT_DELAY = 0.1       # Delay between LLM calls (seconds)
MAX_RETRIES = 3              # Maximum retries for failed LLM calls

# Database settings
EDGE_TABLE_NAME = "edges"
CANON_CLAIMS_TABLE = "canon_claims"
CLAIMS_TABLE = "claims"

# Classification confidence thresholds
HIGH_CONFIDENCE_THRESHOLD = 0.8
MEDIUM_CONFIDENCE_THRESHOLD = 0.6
LOW_CONFIDENCE_THRESHOLD = 0.4

# Relationship types
SUPPORTED_RELATIONSHIP_TYPES = ["supports", "opposes", "neutral"]

# Metadata keys for edges
METADATA_KEYS = {
    'confidence': 'confidence',
    'reasoning': 'reasoning', 
    'similarity_score': 'similarity_score',
    'classified_at': 'classified_at',
    'classifier_version': 'classifier_version'
}
