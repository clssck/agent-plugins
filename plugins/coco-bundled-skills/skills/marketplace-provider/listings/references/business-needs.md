# Business Needs Reference

Used by Path A (A2 metadata generation) and Path C (rejection fixes) of the listings skill.

When adding `business_needs` to a listing, each entry requires **both**:
- `name`: selected from the official list below (or `type: CUSTOM` for a custom need)
- `description`: a **specific 1-2 sentence use case** describing how this listing solves that business need

## Example with description

```yaml
business_needs:
  - name: "Foot Traffic Analytics"
    description: "Enables retailers to optimize store locations using foot traffic patterns from 50M+ devices across the US, with daily refresh and ZIP-code level granularity."
  - name: "Location Planning"
    description: "Supports site selection decisions for new retail locations by combining demographic data with trade area analysis."
```

## Custom business need (if none in the list fits)

```yaml
business_needs:
  - name: "Your Custom Need Name"
    description: "Description of the business problem this data solves"
    type: CUSTOM
```

---

## Official Business Needs List

| Business Need | Best fit for |
|---|---|
| 360-Degree Customer View | Customer data, identity, CRM enrichment |
| Supply Chain | Logistics, inventory, supplier data |
| Personalize Customer Experiences | Behavioral, audience, or preference data |
| Inventory Management | Retail, CPG, operations data |
| Accelerating Advertising Revenue | Ad tech, media, publisher data |
| Attribution Analysis | Marketing, campaign, conversion data |
| Contact Data Enrichment | B2B contact, firmographic, email data |
| Foot Traffic Analytics | Location, geospatial, mobility data |
| Audience Segmentation | Demographic, psychographic, behavioral data |
| Sentiment Analysis | Social, news, review, NLP data |
| ESG Investment Analysis | ESG scores, sustainability data |
| Fundamental Analysis | Financial statements, earnings data |
| Quantitative Analysis | Pricing, time-series, quant signals |
| Risk Analysis | Credit, fraud, compliance, market risk data |
| Fraud Remediation | Fraud signals, identity verification |
| Customer Onboarding | KYC, identity, verification data |
| Identity Resolution | Identity graph, cross-device, PII linking |
| Asset Valuation | Real estate, vehicle, asset pricing data |
| Economic Impact Analysis | Macro economic, GDP, trade, labor data |
| Demand Forecasting | Sales signals, consumer trends |
| Population Health Management | Claims, clinical, public health data |
| Real World Data (RWD) | Clinical trial, patient outcomes |
| Location Planning | Site selection, trade area, POI data |
| Regulatory Reporting | Compliance, regulatory filings |
| Subscriber Acquisition and Retention | Telecom, SaaS, churn data |
| Life Sciences Commercialization | Pharma, biotech, clinical data |
| Patient 360 | Patient records, claims, care journey |
| Blockchain Analysis | Crypto, on-chain transaction data |
| Customer Acquisition | Prospecting, lead enrichment, intent data |
| Data Quality and Cleansing | Reference data, standardization |
| Location Data Enrichment | Address validation, geocoding, POI |
| Location Geocoding | Lat/long, address-to-coordinate data |
| Machine Learning | Training datasets, feature stores |
| Market Analysis | Industry reports, competitive intelligence |
| Pricing Analysis | Price benchmarks, competitive pricing |
| Audience Activation | Programmatic, DSP/SSP, addressable audiences |

---

## Best Practices

- **Pick 2-3 business needs** that are most precise for your data — quality over quantity
- **Each description must be specific to your dataset** — generic descriptions like "helps with marketing" will be flagged in review
- **Reference actual data in the description** when possible (e.g., "50M+ devices", "ZIP-code level", "daily refresh") to make the value tangible
