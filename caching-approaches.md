# Caching Layer Design for WebSearch-LLM

## Overview

A multi-tier caching strategy to reduce latency, API costs, and improve user experience by caching at different stages of the processing pipeline.

---

## Caching Layers

### 1. **Response Cache (L1 - Highest Priority)**

**What to Cache**: Complete answer responses for identical queries

**Cache Key Strategy**:

```python
cache_key = hash(query + target_domain + max_results + max_chunks)
# Example: "prohibited_items_westjet_3_5_v1"
```

**Storage Options**:

**Option A: DynamoDB** (Recommended for serverless)

- **Table Schema**:
  ```
  PK: query_hash (String)
  SK: timestamp (Number, for TTL)
  query_text: Original query text
  target_domain: Domain searched
  response: Complete JSON response
  hit_count: Number of cache hits
  ttl: Expiration timestamp
  ```
- **Benefits**: Serverless, pay-per-use, no cold starts, global tables for multi-region
- **Cost**: ~$0.25-1.25 per million requests (on-demand)
- **TTL**: 1-24 hours depending on content freshness requirements

**Option B: ElastiCache (Redis/Memcached)**

- **Benefits**: Sub-millisecond latency, advanced features (pub/sub, sorted sets)
- **Drawbacks**: Always-on cost (~$15-50/month), VPC complexity, cold starts
- **Use Case**: High-traffic scenarios (>10,000 requests/day)

**Cache Invalidation**:

- Time-based TTL (e.g., 6 hours for general content, 1 hour for dynamic content)
- Manual invalidation API endpoint for content updates
- LRU eviction for size-limited caches

---

### 2. **Search Results Cache (L2)**

**What to Cache**: Raw search results (URLs) from Brave/SerpAPI/DuckDuckGo

**Cache Key Strategy**:
```python
cache_key = f"search_{hash(query + target_domain + max_results)}"
```

**Rationale**:

- Search results change slowly for most queries
- Avoid repeated API calls to paid search services
- Reduce dependency on external APIs

**DynamoDB Schema**:

```
PK: search_hash
urls: List of URLs (StringSet or JSON)
search_provider: "brave" | "serpapi" | "duckduckgo"
query_text: Original query
ttl: 12-24 hours
```

**Benefits**:

- Saves $0.005-0.01 per cached search (Brave/SerpAPI)
- Reduces external API latency (200-500ms)
- Provides fallback if search API is down

---

### 3. **Scraped Content Cache (L3)**

**What to Cache**: Scraped and processed content from URLs

**Cache Key Strategy**:
```python
cache_key = f"content_{hash(url)}"
```

**Rationale**:

- Website content changes slowly (especially documentation)
- Scraping is the slowest part (1-3 seconds per URL)
- Reduces load on target websites

**DynamoDB Schema**:
```
PK: url_hash
url: Original URL
content: Scraped text content (up to 400KB)
last_scraped: Timestamp
etag: HTTP ETag if available
ttl: 24-72 hours (longer for docs, shorter for news)
```

**Smart Invalidation**:
- Use HTTP ETag/Last-Modified headers to check if content changed
- Conditional scraping: only re-scrape if ETag changed

**Benefits**:
- Eliminates scraping time (1-3s per URL)
- Reduces network failures
- Decreases load on target website

---

### 4. **Embedding Cache (L4)**

**What to Cache**: Pre-computed embeddings for frequently accessed chunks

**Cache Key Strategy**:
```python
cache_key = f"embed_{hash(chunk_text)}"
```

**Rationale**:
- Bedrock Titan embedding calls cost money ($0.0001 per 1000 tokens)
- Same chunks appear across multiple queries
- Embedding computation is deterministic

**DynamoDB Schema**:
```
PK: chunk_hash
chunk_text: Text content (for debugging)
embedding: Embedding vector (List of floats or binary)
model: "amazon.titan-embed-text-v1"
ttl: 7-30 days (embeddings don't expire)
```

**Benefits**:
- Saves $0.0001-0.001 per cached embedding
- Reduces Bedrock API latency (100-300ms per batch)
- Enables faster semantic ranking

**Trade-offs**:
- Storage cost: ~1536 floats × 4 bytes = 6KB per embedding
- DynamoDB item size limit: 400KB (can store ~60 embeddings per item)

---

## Implementation Architecture

### Cache Service Class

```python
# src/cache_service.py

class CacheService:
    def __init__(self, dynamodb_table_name, ttl_hours=6):
        self.table = boto3.resource('dynamodb').Table(dynamodb_table_name)
        self.ttl_hours = ttl_hours

    # L1: Response cache
    def get_response(self, query, domain, max_results, max_chunks):
        cache_key = self._hash_query(query, domain, max_results, max_chunks)
        # Check DynamoDB, return if found

    def put_response(self, query, domain, max_results, max_chunks, response):
        # Store in DynamoDB with TTL

    # L2: Search results cache
    def get_search_results(self, query, domain, max_results):
        # Similar pattern

    def put_search_results(self, query, domain, max_results, urls):
        # Store URLs

    # L3: Scraped content cache
    def get_scraped_content(self, url):
        # Check cache by URL hash

    def put_scraped_content(self, url, content, etag=None):
        # Store content with ETag

    # L4: Embedding cache
    def get_embedding(self, chunk_text):
        # Check if embedding exists

    def put_embedding(self, chunk_text, embedding):
        # Store embedding vector

    def batch_get_embeddings(self, chunk_texts):
        # Batch retrieve multiple embeddings
        # Return dict: {chunk_text: embedding or None}
```

---

## Integration Points

### In app.py (Main Handler)

```python
def process_query(self, query, max_results, max_chunks):
    # L1: Check response cache
    cached_response = self.cache_service.get_response(
        query, self.target_domain, max_results, max_chunks
    )
    if cached_response:
        logger.info("Response cache HIT")
        return cached_response

    # L2: Check search results cache
    urls = self.cache_service.get_search_results(query, self.target_domain, max_results)
    if not urls:
        urls = self.search_service.search(...)
        self.cache_service.put_search_results(query, self.target_domain, max_results, urls)

    # L3: Check scraped content cache
    documents = []
    for url in urls:
        cached_content = self.cache_service.get_scraped_content(url)
        if cached_content:
            documents.append(cached_content)
        else:
            content = self.scraper_service.scrape_url(url)
            self.cache_service.put_scraped_content(url, content)
            documents.append(content)

    # Process chunks...
    chunks = self.text_processor.chunk_documents(documents)

    # L4: Batch check embedding cache
    cached_embeddings = self.cache_service.batch_get_embeddings(chunks)
    # Only compute embeddings for cache misses

    # Rank, generate answer...

    # L1: Store response in cache
    self.cache_service.put_response(query, self.target_domain, max_results, max_chunks, result)

    return result
```

---

## Cache Warming Strategy

### Pre-populate Common Queries

```python
# scripts/warm_cache.py
common_queries = [
    "What are the baggage fees?",
    "What items are prohibited?",
    "When can I check in?",
    # ... top 50-100 queries
]

for query in common_queries:
    # Make request to Lambda to populate cache
    # Run during off-peak hours
```

---

## CloudFormation Changes

### DynamoDB Table

```yaml
CacheTable:
  Type: AWS::DynamoDB::Table
  Properties:
    TableName: websearch-llm-cache
    BillingMode: PAY_PER_REQUEST  # On-demand for variable traffic
    TimeToLiveSpecification:
      Enabled: true
      AttributeName: ttl
    AttributeDefinitions:
      - AttributeName: cache_key
        AttributeType: S
      - AttributeName: cache_type
        AttributeType: S
    KeySchema:
      - AttributeName: cache_key
        KeyType: HASH
      - AttributeName: cache_type
        KeyType: RANGE
    GlobalSecondaryIndexes:
      - IndexName: query-index
        KeySchema:
          - AttributeName: query_text
            KeyType: HASH
        Projection:
          ProjectionType: ALL
    Tags:
      - Key: Purpose
        Value: WebSearch-LLM-Cache

# IAM permissions for Lambda to access DynamoDB
CachePolicyStatement:
  - Effect: Allow
    Action:
      - dynamodb:GetItem
      - dynamodb:PutItem
      - dynamodb:Query
      - dynamodb:BatchGetItem
      - dynamodb:BatchWriteItem
    Resource:
      - !GetAtt CacheTable.Arn
      - !Sub "${CacheTable.Arn}/index/*"
```

---

## Monitoring & Metrics

### CloudWatch Metrics to Track

1. **Cache Hit Rate**: `cache_hits / (cache_hits + cache_misses)`
2. **Cache Latency**: Time to retrieve from cache
3. **Cache Size**: Number of items in DynamoDB
4. **TTL Expirations**: Items removed due to TTL
5. **Cost Savings**: Estimated API calls avoided

### Custom Metrics

```python
cloudwatch = boto3.client('cloudwatch')

def record_cache_metric(cache_type, hit):
    cloudwatch.put_metric_data(
        Namespace='WebSearchLLM',
        MetricData=[{
            'MetricName': 'CacheHitRate',
            'Dimensions': [
                {'Name': 'CacheType', 'Value': cache_type}
            ],
            'Value': 1 if hit else 0,
            'Unit': 'None'
        }]
    )
```

---

## Cost Analysis

### Without Caching (Current)
```
1000 requests/month:
- Bedrock LLM: $1.50
- Bedrock Embeddings: $0.50
- Brave Search: $5-10
- Lambda: $2.50
Total: ~$10/month
```

### With Caching (80% hit rate)
```
1000 requests/month (200 unique, 800 cached):
- Bedrock LLM: $0.30 (200 requests)
- Bedrock Embeddings: $0.10 (200 requests)
- Brave Search: $1-2 (200 requests)
- Lambda: $1.00 (200 full, 800 cache-only)
- DynamoDB: $0.50 (read/write)
Total: ~$3/month (70% savings)
```

---

## Recommended Approach

### Phase 1: Response Cache Only (Quick Win)
- Implement L1 response caching with DynamoDB
- 1-2 hours development time
- Immediate 60-80% cost reduction for repeated queries
- Minimal complexity

### Phase 2: Add Search & Content Caching
- Add L2 (search) and L3 (scraped content) caching
- Further reduce latency and external API calls
- 3-4 hours development time

### Phase 3: Embedding Cache (Optional)
- Add L4 embedding caching if Bedrock costs are high
- Most complex, best for high-volume scenarios
- 4-6 hours development time

---

## Alternative: In-Memory Cache (Lambda Global Variables)

For **extremely hot queries**, use Lambda global variables:

```python
# Global cache (persists across invocations in same container)
_response_cache = {}
_max_cache_size = 50

def lambda_handler(event, context):
    query_hash = hash(query)

    # Check in-memory cache first
    if query_hash in _response_cache:
        return _response_cache[query_hash]

    # ... process query ...

    # Store in memory (LRU eviction)
    if len(_response_cache) >= _max_cache_size:
        _response_cache.pop(next(iter(_response_cache)))
    _response_cache[query_hash] = result

    return result
```

**Benefits**:
- Zero latency (in-process)
- Zero cost
- No external dependencies

**Drawbacks**:
- Limited size (~50-100 items)
- Lost on cold start
- Not shared across Lambda instances

---

# Semantic Similarity Cache Design (L1 Enhanced)

## The Problem with Exact Matching

**Current approach** (hash-based):
```python
# These would be DIFFERENT cache entries:
"What are the baggage fees?"
"What are baggage fees?"          # Missing "the"
"What is the cost of checked bags?" # Same intent!
"How much for luggage?"           # Same intent!
```

Only exact matches hit the cache, missing semantically identical queries.

---

## Semantic Similarity Cache Solution

### Architecture Overview

Instead of exact hash matching, use **embedding similarity** to find "close enough" queries:

```
User Query → Embed → Find Similar Cached Queries → Return Cached Response
                ↓
            Similarity > threshold (e.g., 0.85)
```

---

## Implementation Design

### DynamoDB Schema (Enhanced)

```python
# Table: websearch-llm-cache
{
    "PK": "response#<uuid>",           # Unique ID for each cached response
    "query_text": "What are the baggage fees?",
    "query_embedding": [0.123, -0.456, ...],  # 1536-dim vector (binary or list)
    "target_domain": "www.westjet.com",
    "max_results": 3,
    "max_chunks": 5,
    "response": {...},                  # Full JSON response
    "hit_count": 42,                    # Number of times returned
    "last_hit": 1234567890,            # Timestamp of last hit
    "ttl": 1234567890                  # Expiration timestamp
}

# GSI: domain-index (for querying by domain)
GSI_PK: target_domain
GSI_SK: last_hit (to find recent queries)
```

---

## Cache Lookup Flow

### Two-Stage Lookup Process

```python
class SemanticCacheService:
    def __init__(self, similarity_threshold=0.85):
        self.threshold = similarity_threshold
        self.embeddings = BedrockEmbeddings(...)
        self.table = boto3.resource('dynamodb').Table('cache-table')

    def get_response(self, query, domain, max_results, max_chunks):
        """
        Stage 1: Embed the query
        Stage 2: Find similar cached queries
        Stage 3: Return best match if similarity > threshold
        """

        # Stage 1: Embed query (required for semantic matching)
        query_embedding = self.embeddings.embed_query(query)

        # Stage 2: Retrieve candidate cache entries
        # Option A: Scan all (small cache)
        # Option B: Use vector database (large cache)
        candidates = self._get_cache_candidates(domain, max_results, max_chunks)

        # Stage 3: Calculate similarity and find best match
        best_match = None
        best_similarity = 0.0

        for candidate in candidates:
            cached_embedding = candidate['query_embedding']
            similarity = self._cosine_similarity(query_embedding, cached_embedding)

            if similarity > self.threshold and similarity > best_similarity:
                best_match = candidate
                best_similarity = similarity

        if best_match:
            logger.info(
                f"Semantic cache HIT: '{query}' matched '{best_match['query_text']}' "
                f"(similarity: {best_similarity:.3f})"
            )
            # Update hit metrics
            self._increment_hit_count(best_match['PK'])
            return best_match['response']

        logger.info(f"Semantic cache MISS: no match above threshold {self.threshold}")
        return None
```

---

## Retrieval Strategies

### Option A: Scan Approach (Simple, Small Cache)

**When to use**: Cache < 1000 entries

```python
def _get_cache_candidates(self, domain, max_results, max_chunks):
    """Scan all cache entries for this domain"""
    response = self.table.query(
        IndexName='domain-index',
        KeyConditionExpression='target_domain = :domain',
        FilterExpression='max_results = :mr AND max_chunks = :mc',
        ExpressionAttributeValues={
            ':domain': domain,
            ':mr': max_results,
            ':mc': max_chunks
        },
        Limit=100  # Only scan recent entries
    )
    return response['Items']
```

**Pros**: Simple, no additional infrastructure
**Cons**: O(n) scan, slow with large cache
**Cost**: ~$0.25 per 1M reads

---

### Option B: Vector Database (OpenSearch/FAISS)

**When to use**: Cache > 1000 entries, high traffic

```python
# Use Amazon OpenSearch with k-NN plugin
from opensearchpy import OpenSearch

class VectorCacheIndex:
    def __init__(self):
        self.client = OpenSearch(...)

    def index_cache_entry(self, entry_id, query_text, query_embedding, response):
        """Store cache entry with vector for similarity search"""
        self.client.index(
            index='cache-vectors',
            id=entry_id,
            body={
                'query_embedding': query_embedding,
                'query_text': query_text,
                'response': response,
                'timestamp': time.time()
            }
        )

    def search_similar(self, query_embedding, threshold=0.85, k=5):
        """Find top-k similar cached queries"""
        response = self.client.search(
            index='cache-vectors',
            body={
                'size': k,
                'query': {
                    'knn': {
                        'query_embedding': {
                            'vector': query_embedding,
                            'k': k
                        }
                    }
                },
                'min_score': threshold  # Similarity threshold
            }
        )
        return response['hits']['hits']
```

**Pros**:
- Fast k-NN search (< 10ms)
- Scales to millions of vectors
- Built-in similarity filtering

**Cons**:
- Additional infrastructure cost (~$50-200/month for OpenSearch)
- More complex setup

**Cost**: ~$0.50-2.00 per million requests

---

### Option C: Hybrid (DynamoDB + In-Memory FAISS)

**Best of both worlds for moderate scale**

```python
import faiss
import numpy as np
import pickle

class HybridSemanticCache:
    def __init__(self):
        self.table = boto3.resource('dynamodb').Table('cache')
        self.index = None  # FAISS index
        self.id_map = {}   # Maps FAISS index position to DynamoDB PK
        self._load_index()

    def _load_index(self):
        """Load FAISS index from S3 or rebuild from DynamoDB"""
        try:
            # Try loading from S3
            s3 = boto3.client('s3')
            index_bytes = s3.get_object(
                Bucket='cache-bucket',
                Key='faiss_index.bin'
            )['Body'].read()
            self.index = pickle.loads(index_bytes)
        except:
            # Rebuild from DynamoDB
            self._rebuild_index()

    def _rebuild_index(self):
        """Scan DynamoDB and build FAISS index"""
        items = self._scan_all_cache_items()

        dimension = 1536  # Titan embedding dimension
        embeddings = []

        for i, item in enumerate(items):
            embeddings.append(item['query_embedding'])
            self.id_map[i] = item['PK']

        # Create FAISS index
        embeddings_array = np.array(embeddings, dtype='float32')
        self.index = faiss.IndexFlatIP(dimension)  # Inner product (cosine similarity)
        faiss.normalize_L2(embeddings_array)      # Normalize for cosine
        self.index.add(embeddings_array)

        # Save to S3 for next Lambda cold start
        self._save_index_to_s3()

    def search_similar(self, query_embedding, threshold=0.85, k=5):
        """Fast in-memory similarity search"""
        query_array = np.array([query_embedding], dtype='float32')
        faiss.normalize_L2(query_array)

        # Search top-k
        similarities, indices = self.index.search(query_array, k)

        # Filter by threshold and get DynamoDB items
        results = []
        for similarity, idx in zip(similarities[0], indices[0]):
            if similarity >= threshold:
                pk = self.id_map[idx]
                item = self._get_dynamo_item(pk)
                results.append((item, similarity))

        return results
```

**Pros**:
- Fast search (< 1ms in-memory)
- No additional infrastructure
- Serverless-friendly (persists in Lambda container)
- Index stored in S3 (rebuilds on cold start)

**Cons**:
- Cold start penalty (~500ms to load index)
- Memory overhead (each Lambda instance has own copy)
- Index updates require rebuild

**Cost**: Minimal (S3 storage only, ~$0.01/month)

---

## Embedding Strategy

### Challenge: Every Query Needs Embedding

**Problem**: Embedding the query to check cache defeats the purpose (adds latency)

**Solutions**:

### 1. **Batch with Query Processing** (Recommended)

```python
def get_response_semantic(self, query, domain, max_results, max_chunks):
    # Embed query once (will be used for ranking anyway)
    query_embedding = self.embeddings.embed_query(query)

    # Check semantic cache
    cached = self._find_similar_cached(query_embedding, domain, ...)
    if cached:
        return cached['response']

    # If miss, continue with normal flow
    # The embedding is reused for chunk ranking!
    # No wasted embedding call
```

**Key insight**: The query embedding is **already needed** for semantic chunk ranking, so we get semantic caching "for free"!

### 2. **Two-Tier Cache**

```python
# L1a: Exact match cache (hash-based, ultra-fast)
exact_match = self._check_exact_cache(query_hash)
if exact_match:
    return exact_match  # 0ms cache hit

# L1b: Semantic cache (embedding-based, slower but flexible)
semantic_match = self._check_semantic_cache(query_embedding)
if semantic_match:
    return semantic_match  # 100ms cache hit

# Miss: Full processing (4-6 seconds)
```

---

## Similarity Threshold Tuning

### Choosing the Right Threshold

```python
# Conservative (avoid false positives)
threshold = 0.90  # Very similar queries only
# "What are baggage fees?" ✓
# "What's the baggage fee?" ✓
# "How much for luggage?" ✗ (might be too different)

# Moderate (balanced)
threshold = 0.85  # Recommended starting point
# Captures paraphrases while avoiding false matches

# Aggressive (maximize cache hits)
threshold = 0.75  # Broader matching
# Risk: returning slightly irrelevant cached answers
```

### A/B Testing Thresholds

```python
# Log similarity scores to find optimal threshold
logger.info(
    f"Cache candidate: '{cached_query}' → '{user_query}' "
    f"similarity: {similarity:.3f}"
)

# Analyze CloudWatch Logs to determine:
# - What similarity scores lead to good matches?
# - Where are false positives happening?
```

---

## Performance Comparison

### Exact Hash Cache
```
Lookup time: 5-10ms (DynamoDB GetItem)
Hit rate: 20-30% (only exact matches)
Cost: $0.25 per 1M requests
```

### Semantic Cache (Scan)
```
Lookup time: 50-200ms (scan + similarity calc)
Hit rate: 60-80% (paraphrases, synonyms)
Cost: $0.25-0.50 per 1M requests
Embedding cost: $0.0001 per query
```

### Semantic Cache (FAISS Hybrid)
```
Lookup time: 5-15ms (in-memory + DynamoDB)
Hit rate: 60-80%
Cost: $0.25 per 1M requests
Embedding cost: $0.0001 per query
```

---

## Recommended Implementation

### Phase 1: Simple Semantic Cache (DynamoDB Scan)

```python
# For low-moderate traffic (< 10,000 requests/day)
class SimpleSemanticCache:
    THRESHOLD = 0.85
    MAX_CANDIDATES = 50  # Limit scan size

    def get_response(self, query, domain, max_results, max_chunks):
        # Already embedding for chunk ranking, reuse it!
        query_embedding = self.embeddings.embed_query(query)

        # Get recent cache entries for this domain
        candidates = self.table.query(
            IndexName='domain-recent-index',
            KeyConditionExpression='target_domain = :domain',
            ScanIndexForward=False,  # Most recent first
            Limit=self.MAX_CANDIDATES
        )['Items']

        # Find best semantic match
        for candidate in candidates:
            similarity = cosine_similarity(
                query_embedding,
                candidate['query_embedding']
            )
            if similarity >= self.THRESHOLD:
                return candidate['response']

        return None
```

### Phase 2: Add FAISS for Scale (Optional)

Only if cache grows > 1,000 entries or traffic increases significantly.

---

## Example Cache Entries

```python
# Original query
{
    "PK": "resp#001",
    "query_text": "What are the baggage fees?",
    "query_embedding": [0.234, -0.123, ...],  # 1536-dim
    "response": {"answer": "Checked baggage fees start at $40..."}
}

# Semantic matches (similarity > 0.85)
"What is the cost of checked bags?"      # 0.92 similarity ✓
"How much for luggage?"                  # 0.87 similarity ✓
"Tell me about baggage charges"          # 0.86 similarity ✓
"What are baggage fees?"                 # 0.95 similarity ✓
"Can I bring a bag for free?"            # 0.73 similarity ✗ (different intent)
```

---

## Monitoring

### Key Metrics

```python
# Semantic cache metrics
- semantic_cache_hits: Count
- semantic_cache_misses: Count
- average_match_similarity: Gauge (0.0-1.0)
- false_positive_rate: Percentage
- embedding_time: Duration (ms)
- similarity_search_time: Duration (ms)

# User feedback mechanism
def rate_cache_response(query, cached_query, helpful: bool):
    """Track if semantic match was actually relevant"""
    cloudwatch.put_metric_data(
        Namespace='SemanticCache',
        MetricData=[{
            'MetricName': 'CacheQuality',
            'Value': 1 if helpful else 0,
            'Dimensions': [
                {'Name': 'Similarity', 'Value': str(round(similarity, 1))}
            ]
        }]
    )
```

---

## Summary

**Semantic similarity caching provides significant advantages over exact matching:**

**Recommended Approach**:
1. Start with simple DynamoDB scan approach (0.85 threshold)
2. Reuse query embedding from chunk ranking (no extra cost)
3. Limit scans to 50-100 recent entries
4. Monitor similarity scores to tune threshold
5. Upgrade to FAISS if cache grows large

**Expected Results**:
- Cache hit rate: 60-80% (vs 20-30% for exact match)
- Added latency: ~100ms (embedding already needed)
- Cost savings: 70-80% reduction in Bedrock/search API calls
- Better UX: Users get cached responses for paraphrased questions

**Key Advantages**:
- **Higher hit rate**: 60-80% vs 20-30% for exact matching
- **Natural language flexibility**: Handles paraphrases, synonyms, rewordings
- **Reuses existing infrastructure**: Query embedding already computed for ranking
- **Tunable accuracy**: Adjust threshold based on use case
- **Cost-effective**: Minimal additional cost using DynamoDB scan approach

This approach provides the best balance of accuracy, performance, and implementation complexity for a serverless architecture!
