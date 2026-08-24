---
name: openflow-nifi-expression-language
description: NiFi Expression Language (EL) syntax and functions. Load when manipulating FlowFile attributes in processor properties.
---

# NiFi Expression Language

The NiFi Expression Language (EL) provides dynamic access to FlowFile attributes and system properties.

**Full documentation:** [Expression Language Guide](https://nifi.apache.org/docs/nifi-docs/html/expression-language-guide.html)
Note: This link is a very large file, only load it if the concise reference in this file is insufficient.

**Scope:** EL manipulates FlowFile **attributes** (metadata). For record field manipulation (JSON/Avro/CSV content), use RecordPath instead. See `nifi-main.md` for when to use each.

---

## Syntax Basics

```
${attribute_name}                    # Access attribute value
${attribute:function()}              # Apply function to attribute
${attribute:function1():function2()} # Chain functions
${literal('text')}                   # Literal string (escape EL syntax)
${'my attribute'}                    # Quote attribute names with special chars
```

**Escaping:** To output literal `${...}`, use `$${}` or `${literal('${...')}`.

---

## Boolean Logic

| Function | Description | Example |
|----------|-------------|---------|
| `isNull()` | True if null | `${attr:isNull()}` |
| `notNull()` | True if not null | `${attr:notNull()}` |
| `isEmpty()` | True if empty string | `${attr:isEmpty()}` |
| `equals(value)` | Equality check | `${status:equals('active')}` |
| `equalsIgnoreCase(value)` | Case-insensitive equality | `${type:equalsIgnoreCase('JSON')}` |
| `gt(value)` | Greater than | `${count:gt(10)}` |
| `ge(value)` | Greater or equal | `${count:ge(10)}` |
| `lt(value)` | Less than | `${count:lt(100)}` |
| `le(value)` | Less or equal | `${count:le(100)}` |
| `and(expr)` | Logical AND | `${a:equals('x'):and(${b:equals('y')})}` |
| `or(expr)` | Logical OR | `${a:isNull():or(${a:isEmpty()})}` |
| `not()` | Logical NOT | `${valid:not()}` |
| `ifElse(true, false)` | Conditional | `${valid:ifElse('yes', 'no')}` |
| `isJson()` | True if valid JSON | `${content:isJson()}` |

---

## String Manipulation

| Function | Description | Example |
|----------|-------------|---------|
| `toUpper()` | Uppercase | `${text:toUpper()}` |
| `toLower()` | Lowercase | `${text:toLower()}` |
| `trim()` | Remove whitespace | `${text:trim()}` |
| `substring(start, end)` | Extract substring | `${filename:substring(0, 10)}` |
| `substringBefore(delim)` | Text before delimiter | `${filename:substringBefore('.')}` |
| `substringBeforeLast(delim)` | Text before last delimiter | `${path:substringBeforeLast('/')}` |
| `substringAfter(delim)` | Text after delimiter | `${filename:substringAfter('.')}` |
| `substringAfterLast(delim)` | Text after last delimiter | `${path:substringAfterLast('/')}` |
| `getDelimitedField(idx, delim)` | Get field from delimited string | `${csv:getDelimitedField(2, ',')}` |
| `append(suffix)` | Append text | `${filename:append('.bak')}` |
| `prepend(prefix)` | Prepend text | `${filename:prepend('backup_')}` |
| `replace(search, repl)` | Replace first occurrence | `${text:replace('old', 'new')}` |
| `replaceFirst(regex, repl)` | Regex replace first | `${text:replaceFirst('[0-9]+', 'N')}` |
| `replaceAll(regex, repl)` | Regex replace all | `${text:replaceAll('[0-9]', 'X')}` |
| `padLeft(len, char)` | Pad left to length | `${id:padLeft(10, '0')}` |
| `padRight(len, char)` | Pad right to length | `${name:padRight(20, ' ')}` |
| `replaceNull(value)` | Default if null | `${attr:replaceNull('default')}` |
| `replaceEmpty(value)` | Default if empty | `${attr:replaceEmpty('default')}` |
| `length()` | String length | `${text:length()}` |
| `repeat(count)` | Repeat string | `${char:repeat(5)}` |

---

## Searching

| Function | Description | Example |
|----------|-------------|---------|
| `startsWith(prefix)` | Starts with string | `${filename:startsWith('log_')}` |
| `endsWith(suffix)` | Ends with string | `${filename:endsWith('.csv')}` |
| `contains(substring)` | Contains string | `${text:contains('error')}` |
| `in(val1, val2, ...)` | Value in list | `${type:in('A', 'B', 'C')}` |
| `find(regex)` | Find regex match | `${text:find('[0-9]+')}` |
| `matches(regex)` | Full regex match | `${id:matches('[A-Z]{3}[0-9]{4}')}` |
| `indexOf(search)` | Index of substring | `${text:indexOf(',')}` |
| `lastIndexOf(search)` | Last index of substring | `${path:lastIndexOf('/')}` |

---

## JSON Functions

| Function | Description | Example |
|----------|-------------|---------|
| `jsonPath(path)` | Extract via JSONPath | `${json:jsonPath('$.name')}` |
| `jsonPathDelete(path)` | Delete via JSONPath | `${json:jsonPathDelete('$.temp')}` |
| `jsonPathAdd(path, val)` | Add via JSONPath | `${json:jsonPathAdd('$.items', 'new')}` |
| `jsonPathSet(path, val)` | Set via JSONPath | `${json:jsonPathSet('$.status', 'done')}` |
| `jsonPathPut(path, k, v)` | Put key-value via JSONPath | `${json:jsonPathPut('$', 'key', 'val')}` |

---

## Encode/Decode

| Function | Description | Example |
|----------|-------------|---------|
| `escapeJson()` | Escape for JSON | `${text:escapeJson()}` |
| `unescapeJson()` | Unescape JSON | `${json:unescapeJson()}` |
| `escapeXml()` | Escape for XML | `${text:escapeXml()}` |
| `escapeCsv()` | Escape for CSV | `${field:escapeCsv()}` |
| `escapeHtml3()` | Escape HTML 3 | `${text:escapeHtml3()}` |
| `escapeHtml4()` | Escape HTML 4 | `${text:escapeHtml4()}` |
| `urlEncode()` | URL encode | `${param:urlEncode()}` |
| `urlDecode()` | URL decode | `${encoded:urlDecode()}` |
| `base64Encode()` | Base64 encode | `${text:base64Encode()}` |
| `base64Decode()` | Base64 decode | `${encoded:base64Decode()}` |
| `hash(algorithm)` | Hash value (MD5, SHA-256, etc.) | `${text:hash('SHA-256')}` |

---

## Type Coercion

| Function | Description | Example |
|----------|-------------|---------|
| `toString()` | Convert to string | `${fileSize:toString()}` |
| `toNumber()` | Convert to integer | `${count:toNumber()}` |
| `toDecimal()` | Convert to decimal | `${price:toDecimal()}` |

---

## Date Functions

| Function | Description | Example |
|----------|-------------|---------|
| `now()` | Current timestamp (no subject) | `${now()}` |
| `format(pattern)` | Format date to string | `${now():format('yyyy-MM-dd')}` |
| `format(pattern, tz)` | Format with timezone | `${ts:format('yyyy-MM-dd HH:mm', 'UTC')}` |
| `toDate(pattern)` | Parse string to date | `${timestamp:toDate('yyyy-MM-dd')}` |
| `toDate(pattern, tz)` | Parse with timezone | `${ts:toDate('yyyy-MM-dd', 'America/New_York')}` |

See `nifi-date-formatting.md` for pattern reference.

---

## Math Functions

| Function | Description | Example |
|----------|-------------|---------|
| `plus(value)` | Addition | `${count:plus(1)}` |
| `minus(value)` | Subtraction | `${count:minus(1)}` |
| `multiply(value)` | Multiplication | `${price:multiply(1.1)}` |
| `divide(value)` | Division | `${total:divide(100)}` |
| `mod(value)` | Modulo | `${index:mod(10)}` |

---

## Subjectless Functions

Called without an attribute reference.

| Function | Description | Example |
|----------|-------------|---------|
| `now()` | Current timestamp | `${now()}` |
| `UUID()` | Generate random UUID | `${UUID()}` |
| `UUID3(namespace, name)` | Generate UUID v3 | `${UUID3('url', 'example.com')}` |
| `UUID5(namespace, name)` | Generate UUID v5 | `${UUID5('dns', 'example.com')}` |
| `hostname()` | System hostname | `${hostname()}` |
| `hostname(fqdn)` | Full hostname if true | `${hostname(true)}` |
| `ip()` | System IP address | `${ip()}` |
| `literal(value)` | Literal string value | `${literal('${not_an_attr}')}` |
| `nextInt()` | Random positive int | `${nextInt()}` |
| `random()` | Random 0.0-1.0 | `${random()}` |
| `thread()` | Current thread name | `${thread()}` |
| `getStateValue(key)` | Get processor state | `${getStateValue('counter')}` |

---

## Multi-Attribute Functions

Evaluate multiple attributes at once.

| Function | Description | Example |
|----------|-------------|---------|
| `anyAttribute(names...)` | Any attr matches condition | `${anyAttribute('a','b'):contains('x')}` |
| `allAttributes(names...)` | All attrs match condition | `${allAttributes('a','b'):notNull()}` |
| `anyMatchingAttribute(regex)` | Any matching attr name | `${anyMatchingAttribute('error.*'):notNull()}` |
| `allMatchingAttributes(regex)` | All matching attr names | `${allMatchingAttributes('count.*'):gt(0)}` |
| `join(delimiter)` | Join results | `${allAttributes('a','b'):join(',')}` |
| `count()` | Count results | `${allMatchingAttributes('.*'):count()}` |

---

## Common Patterns

### Null-Safe Default

```
${attr:replaceNull('default_value')}
${attr:isEmpty():ifElse('default', ${attr})}
```

### Conditional Routing

```
${status:equals('active'):and(${count:gt(0)})}
```

### Dynamic Filename

```
${uuid}_${now():format('yyyyMMdd_HHmmss')}.json
```

### Extract from Delimited

```
# Get 3rd field from comma-separated
${csv_line:getDelimitedField(3, ',')}
```

---

## Related References

- `nifi-main.md` - NiFi reference router
- `nifi-recordpath.md` - For record field manipulation
- `nifi-date-formatting.md` - Date pattern reference
