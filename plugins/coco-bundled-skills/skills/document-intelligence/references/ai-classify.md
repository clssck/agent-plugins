# AI_CLASSIFY

Classify text or images into user-defined categories (single or multi-label).

**Docs**: [docs.snowflake.com/en/sql-reference/functions/ai_classify](https://docs.snowflake.com/en/sql-reference/functions/ai_classify) — full syntax, parameters (input, categories, config_object), return format, category definitions with descriptions, few-shot examples, usage notes, limitations, and stage restrictions.

---

## Usage Patterns

### Pattern 1: Basic Single-Label
Classify text into one category from a fixed set.

**Trigger**: "classify", "categorize", "which category", "single label"

```sql
SELECT 
    text,
    AI_CLASSIFY(text, ['travel', 'cooking', 'fitness']):labels[0]::VARCHAR AS category
FROM documents;
```

### Pattern 2: Multi-Label Classification
Assign multiple tags/labels to content.

**Trigger**: "multi-label", "multiple tags", "all applicable categories", "tagging"

```sql
SELECT 
    article_text,
    AI_CLASSIFY(
        article_text,
        ['technology', 'finance', 'healthcare', 'sports'],
        {'output_mode': 'multi'}
    ):labels AS tags
FROM articles;
```

### Pattern 3: Sentiment Classification
Classify text by sentiment or emotion.

**Trigger**: "sentiment", "emotion", "positive/negative", "mood"

```sql
-- Basic sentiment
SELECT 
    review,
    AI_CLASSIFY(review, ['positive', 'negative', 'neutral']):labels[0]::VARCHAR AS sentiment
FROM reviews;

-- Fine-grained emotions (GO_EMOTIONS dataset pattern)
SELECT 
    text,
    AI_CLASSIFY(
        text,
        ['joy', 'sadness', 'anger', 'fear', 'surprise', 'disgust']
    ):labels[0]::VARCHAR AS emotion
FROM messages;
```

### Pattern 4: Topic Classification
Classify content by topic or subject area.

**Trigger**: "topic", "subject", "what is this about", "categorize articles"

```sql
-- News categorization
SELECT 
    headline,
    AI_CLASSIFY(
        headline,
        ['world', 'politics', 'business', 'technology', 'sports', 'entertainment']
    ):labels[0]::VARCHAR AS topic
FROM news_articles;

-- Paper/document topics (multi-label)
SELECT 
    abstract,
    AI_CLASSIFY(
        abstract,
        ['machine learning', 'natural language processing', 'computer vision', 'robotics'],
        {'output_mode': 'multi'}
    ):labels AS topics
FROM papers;
```

### Pattern 5: Support Ticket Routing
Route tickets or requests to appropriate teams.

**Trigger**: "route tickets", "triage", "assign to team", "support category"

```sql
SELECT 
    ticket_text,
    AI_CLASSIFY(
        ticket_text,
        ['billing', 'technical_support', 'account_access', 'feature_request', 'bug_report'],
        {'task_description': 'Classify support ticket to route to appropriate team'}
    ):labels[0]::VARCHAR AS assigned_team
FROM support_tickets;
```

### Pattern 6: Intent Classification
Detect user intent from queries or messages.

**Trigger**: "intent", "what does user want", "user request type", "banking intent"

```sql
-- Banking intents (BANKING77 pattern)
SELECT 
    query,
    AI_CLASSIFY(
        query,
        ['check_balance', 'transfer_money', 'card_blocked', 'loan_inquiry', 'account_closure']
    ):labels[0]::VARCHAR AS intent
FROM customer_queries;
```

### Pattern 7: Image Classification
Classify images into visual categories.

**Trigger**: "classify image", "image category", "what's in the picture", "visual classification"

```sql
-- Product categorization
SELECT 
    filepath,
    AI_CLASSIFY(
        TO_FILE(file_url),
        ['electronics', 'clothing', 'furniture', 'food', 'toys'],
        {'model': 'pixtral-large'}
    ):labels[0]::VARCHAR AS product_category
FROM product_images;

-- Fashion classification (hierarchical)
SELECT 
    AI_CLASSIFY(
        TO_FILE(image_url),
        ['tops', 'bottoms', 'dresses', 'outerwear', 'accessories']
    ):labels[0]::VARCHAR AS clothing_type
FROM fashion_catalog;

-- Real estate room classification
SELECT 
    AI_CLASSIFY(
        TO_FILE('@my_images', 'room.jpg'),
        ['living_area', 'kitchen', 'bathroom', 'bedroom', 'garden']
    ):labels[0]::VARCHAR AS room_type;
```

### Pattern 8: With Task Description
Provide context to improve classification accuracy.

**Trigger**: "need context", "ambiguous categories", "custom classification"

```sql
SELECT 
    text,
    AI_CLASSIFY(
        text,
        ['travel', 'cooking', 'fitness'],
        {
            'task_description': 'Classify the hobby mentioned in the text'
        }
    ):labels[0]::VARCHAR AS hobby
FROM user_posts;
```

### Pattern 9: With Few-Shot Examples
Improve accuracy with example classifications.

**Trigger**: "few-shot", "examples", "train with samples", "edge cases"

```sql
SELECT 
    text,
    AI_CLASSIFY(
        text,
        [
            {'label': 'travel', 'description': 'content about traveling'},
            {'label': 'cooking', 'description': 'content about preparing food'},
            {'label': 'reading', 'description': 'content about books'}
        ],
        {
            'task_description': 'Determine topics in the text',
            'output_mode': 'multi',
            'examples': [
                {
                    'input': 'I love traveling with a good book',
                    'labels': ['travel', 'reading'],
                    'explanation': 'mentions traveling and reading'
                }
            ]
        }
    ):labels AS topics
FROM posts;
```

### Pattern 10: Dynamic Categories from Table
Categories derived from data rather than hardcoded.

**Trigger**: "categories from table", "dynamic labels", "labels in column"

```sql
WITH
labels AS (
    SELECT ARRAY_AGG(DISTINCT category) AS label_list
    FROM category_definitions
),
data AS (
    SELECT id, text FROM documents
)
SELECT 
    d.id,
    d.text,
    AI_CLASSIFY(d.text, l.label_list):labels[0]::VARCHAR AS category
FROM data d, labels l;
```

### Pattern 11: Hierarchical Classification
Classify at multiple levels of a taxonomy.

**Trigger**: "hierarchical", "parent/child categories", "fine-grained", "sublevel"

```sql
-- First level: broad category
SELECT 
    product_id,
    AI_CLASSIFY(TO_FILE(image_url), ['clothing', 'electronics', 'home']):labels[0]::VARCHAR AS main_category,
    -- Second level: specific type (conditional on first)
    CASE 
        WHEN main_category = 'clothing' THEN
            AI_CLASSIFY(TO_FILE(image_url), ['shirts', 'pants', 'dresses', 'shoes']):labels[0]::VARCHAR
    END AS sub_category
FROM products;
```

## Examples by Client Question

| Client Question | Pattern | SQL |
|-----------------|---------|-----|
| "Categorize reviews by sentiment" | Sentiment | `AI_CLASSIFY(review, ['positive', 'negative', 'neutral'])` |
| "Tag articles with multiple topics" | Multi-Label | `AI_CLASSIFY(text, [...], {'output_mode': 'multi'})` |
| "Route support tickets" | Ticket Routing | `AI_CLASSIFY(ticket, ['billing', 'tech', ...])` |
| "Classify product images" | Image | `AI_CLASSIFY(TO_FILE(url), categories)` |
| "Detect user intent" | Intent | `AI_CLASSIFY(query, ['check_balance', ...])` |
| "Classify with examples" | Few-Shot | `AI_CLASSIFY(text, categories, {'examples': [...]})` |
| "What emotion is this?" | Sentiment | `AI_CLASSIFY(text, ['joy', 'sadness', 'anger', ...])` |
| "Categorize StackOverflow questions" | Topic | `AI_CLASSIFY(text, tags, {'output_mode': 'multi'})` |

## Performance Tips

- **Category limit**: Up to 500 labels supported, but >20 may reduce accuracy
- **Label descriptions**: Add descriptions for ambiguous categories
- **Few-shot examples**: Provide 1-3 examples for edge cases
- **Case sensitivity**: Both input and categories are case-sensitive

## Access Control

Requires `SNOWFLAKE.CORTEX_USER` database role.

## Limitations

- Image classification requires multimodal models (`pixtral-large`, `claude-3-5-sonnet`)
- Does not work with `SNOWFLAKE_FULL` encrypted internal stages
- Does not work with customer-side encrypted external stages
