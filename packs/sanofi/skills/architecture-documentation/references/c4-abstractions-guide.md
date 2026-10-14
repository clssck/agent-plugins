# C4 Abstractions Guide

Definitions, boundary rules, and common mistakes for the four C4 abstractions: Person, Software System, Container, Component. Classify by runtime responsibility; repo layout, team ownership, and provisioning are evidence, never the rule. Closes with the Sanofi Systems-vs-Stores framework and its C4 mapping.

---

## Person

**Definition**: human user of the software system; the human actors that interact directly with it.

**Roles vs. named individuals:**
- **Roles** in most diagrams ("Pharmacist", "Administrator", "Patient")
- **Named individuals** only in team-specific deployment or org-chart diagrams
- Several roles may interact with one system differently

**Naming:** `[Role] [Optional: Organization/Context]`; short but specific enough to distinguish roles. Examples: `Pharmacist (Retail)`, `Clinical Trial Manager`, `Data Analyst`, `External Auditor`

**Description template:**
> [Role name] who [primary interaction with system]. Responsible for [key tasks].

**Examples:**

| Name | Description |
|------|-------------|
| Pharmacist (Retail) | Verifies prescriptions and manages drug inventory using the platform |
| Clinical Trial Manager | Designs and monitors clinical study protocols and patient enrollment |
| System Administrator | Configures system settings, manages users, and monitors operations |
| External Auditor | Reviews compliance reports and audit trails for regulatory inspections |

---

## Software System

**Definition**: highest C4 abstraction; something that delivers value to users, human or automated. The overall "application" or "product" being documented.

**Scope evidence (not fixed rules):**
- Clear business purpose, users, and boundary useful to the diagram's audience.
- Team ownership, repository layout, deployment topology, release cadence are evidence; none alone defines a boundary.
- One repository can hold several systems; one system can span several repositories or teams.

**Boundary questions:**
- **User-facing purpose**: distinct capability or value proposition to users or other systems?
- **Lifecycle and governance**: planned, operated, secured, changed as a coherent product/application boundary?
- **Relationship clarity**: would separate modeling clarify dependencies and responsibilities for the audience?

**What organizations call it:**
- "Application" -> Software System
- "Product" -> Software System
- "Service" (in the business sense, not microservice) -> Software System
- "Platform" -> May be one system or a system landscape of multiple systems

**What is NOT a Software System:**
- Product domains
- Bounded contexts
- Business capabilities
- Feature teams, tribes, or squads
- Tools or frameworks (React, Fastify, Drizzle, Terraform, etc.)

Organizational or strategic concepts, not software systems. A software system is a concrete thing a team builds, deploys, and maintains.

**In-scope vs. external:**
- System under documentation: **blue** (#0047BB), at the center
- External systems (other teams' systems, third-party services): **grey** (#6D6E71)
- "External" = anything outside the documented software-system boundary, regardless of team ownership

**Naming convention:** `[Product Name] System`
Examples: `User Platform System`, `Clinical Trial Management System`, `Order Processing System`

---

## Container

**Definition**: application or data store that must run for the system to work. A **separately runnable/deployable unit** that executes code or stores data; a runtime process boundary.

**IMPORTANT**: C4 "container" ≠ Docker container. Docker is a deployment mechanism; a C4 container is an architectural abstraction.

### What IS a Container

| Type | Examples | Suggested visual distinction |
|------|----------|-----------------------------|
| Web application (server-side) | Express server, Fastify API, NestJS app | Application |
| Single-page application (client-side) | React app running in the browser | Application |
| Mobile application | iOS app, Android app | Application |
| Desktop application | Electron app | Application |
| API service | REST API, GraphQL server, gRPC service | Application |
| Background worker | Queue consumer, scheduler, cron job runner | Application |
| Serverless function | AWS Lambda, Azure Function | Application |
| Database | PostgreSQL, MySQL, DynamoDB, MongoDB | Data store |
| In-memory cache/store | Redis, Memcached, ElastiCache | Data store |
| Individual queue / topic / stream | SQS queue, SNS topic, Kafka topic, RabbitMQ queue | Messaging/data store |
| Object/blob storage | S3 bucket (that you own and manage) | Data store |
| File system | Shared file storage, EFS | Data store |
| CDN | CloudFront distribution (that you configure) | Delivery/runtime service |
| Shell script | Batch processing script that runs as a process | Application |

### What IS NOT a Container

| Not a Container | Why | What It Actually Is |
|----------------|-----|-------------------|
| JAR file | Code packaging format, not a runtime boundary | Part of a container (Java app) |
| C# assembly / DLL | Compiled library, loaded into a process | Part of a container (.NET app) |
| npm package | Dependency installed into a project | Part of a container (Node.js app) |
| Python module/package | Importable code within a project | Part of a container (Python app) |
| Shared library (.so) | Dynamically linked at runtime in a process | Part of a container |
| Terraform module | Infrastructure definition, not running code | Infrastructure concern |
| Dockerfile | Build recipe, not the running application | Deployment concern |
| AWS Bedrock Agent | Managed platform; your agent configuration may be an in-scope responsibility | Provider platform external; your agent a container only if in scope and relevant |
| Step Functions state machine | Managed engine runs your workflow definition | Your workflow is a container if in scope; the Step Functions service is external |
| EventBridge rule/pipe | Managed event routing | External system, or part of the owning container when you own the rule |
| Individual Lambda (in multi-Lambda API) | One function behind a shared API Gateway | Part of a container (the API service) |
| Tool or framework (Fastify, Drizzle, React, etc.) | Technology choice, not an architectural unit | Annotate as [Technology] on the container that uses it |

### Key Rules

**Browser SPA and server-side runtime:**
A browser SPA is normally a client-side container. Add an API, asset host, or other server-side runtime as a container only when it is a distinct in-scope runtime or data-store responsibility. The API may serve the SPA assets, deploy separately, or be external to the documented system; do not infer a second container solely from a frontend repository or development server.

```
In-scope SPA + API (two containers):
  [User Platform SPA]        -- React app running in user's browser
  [User Platform API]        -- Fastify / TypeScript server
  Arrow: "Fetches user data [HTTP/REST JSON]"

SPA with an external API (one in-scope container plus external system):
  [User Platform SPA]        -- React app running in user's browser
  [Identity Platform]        -- External system
```

**Managed cloud services:**
Within the documented boundary and relevant to the view → container. Merely consumed → external system. No help to the audience → omit. Ownership and provisioning are evidence, not automatic classification.

**Single deployment, multiple containers:**
Do not collapse distinct runtime or data-store responsibilities because local development starts them together; do not split implementation details lacking independent runtime meaning. Deployment topology → Deployment diagrams.

**Queues, topics, and message buses:**
Each queue or topic you own is a data-store container. NEVER model the broker itself (Kafka cluster, RabbitMQ server) as one hub container: a hub hides producer-consumer coupling. Alternative: omit the queues and put the queue name in the relationship label ("Sends order events via `orders-queue` to"). Both valid; keep one choice per diagram set. The broker or cluster belongs on the Deployment diagram. Separate software systems sharing a queue need a stated owner (producer, consumer, or third party).

**Microservices:**
Within a single software system, each microservice is a group of one or more containers (API plus data store) inside one system boundary. Promote a service to its own software system only when it carries a distinct runtime responsibility with its own boundary; a separate owning and operating team is evidence for that, never the deciding rule.

---

## Component

**Definition**: grouping of related functionality behind a well-defined interface. Lives inside a container; NOT separately deployable.

**Grouping strategies:**
- **Layered**: Controllers, Services, Repositories, Middleware
- **Feature/domain**: UserModule, OrderModule, PaymentModule
- **Hexagonal**: Adapters (driving/driven), Application Services, Domain Services
- **Hybrid**: Group by architectural significance, using whatever organization
  best communicates the container's internal structure

**Hexagonal architecture — Ports:**
Ports (inbound and outbound) are **interfaces/contracts**, not components: inbound = what the container offers, outbound = what it requires. NEVER model ports as components in L3. Document them as **notes on the container** in L2 (e.g., "Inbound: REST API, Event Listener"; "Outbound: Database, Message Queue"). The C4 components in a hexagonal codebase are the **Adapters** (implementations) and **Services** (use cases, domain logic).

**What IS NOT a component:**

| Not a Component | Why |
|----------------|-----|
| Folder / directory | Organizational structure, not an architectural unit |
| Namespace | Language scope mechanism, not a runtime grouping |
| Package (npm, pip) | Dependency management unit |
| Class (individual) | Too granular for C4 L3 -- belongs at L4 (Code) |
| Utility / helper file | Infrastructure code, not architecturally significant |
| Config file | Not functional code |
| Data model class | Supporting code, not a component boundary |
| Port (inbound/outbound) | Interface/contract, not an implementation -- document as a note on the container instead |
| Tool / framework | Technology choice, not a responsibility -- annotate as a comment on the component that uses it |

**Design strategy:**
1. Identify the container's major responsibilities
2. Group related code elements by responsibility
3. Define clear interfaces between groups
4. Exclude noise: data models, utilities, config, constants
5. Include only responsibilities needed to explain the container to the audience; C4 has no fixed component-count target
6. Split, regroup, or omit detail when the view stops answering a useful architectural question or becomes hard to read

---

## Common Mistakes

| Mistake | Why It Is Wrong | Correction |
|---------|----------------|------------|
| Inventing or omitting a SPA runtime | A browser client, asset host, and API may have different system boundaries | Model each distinct in-scope runtime; show external dependencies as external systems |
| Modeling npm packages as containers | Packages are code organization, not runtime | They are part of the container they install into |
| Modeling S3 as external system | If you own and manage the bucket, it is your container | Model as a container within your system boundary |
| Modeling folders as components | Folders are filesystem organization | Group by architectural responsibility instead |
| Using "Uses" as relationship label | Too generic, gives no useful information | Be specific: "Reads user profiles from", "Sends events to" |
| Missing technology labels | Containers and components need technology context | Always include [Technology] annotation |
| Showing deployment details in L2 | Load balancers, AZs, replicas belong in Deployment | Keep L2 focused on logical architecture |
| Mixing abstraction levels | Having both systems and components in one diagram | Each diagram SHOULD be one C4 level |
| Bidirectional arrows | C4 uses unidirectional relationships | Two separate arrows if communication goes both ways |
| Person interacting with database directly | Users interact with applications, not databases | Route through the application container |
| Modeling tools/frameworks as elements | Frameworks are technology choices, not architectural units | Annotate as [Technology] label or comment on the element that uses them |
| Modeling each Lambda as a container | Multiple Lambdas behind one API Gateway are one service | Consolidate into one container (see [Serverless Consolidation Pattern](skill://architecture-documentation/references/codebase-analysis-patterns.md#serverless-consolidation-pattern)) |
| Treating every managed service as a container or as external | Classification follows scope and responsibility, not provisioning | Apply the managed-cloud-service rule; your Lambda action groups are containers either way |

---

## Sanofi Modeling Framework

### Systems vs. Stores

Sanofi architecture governance distinguishes:

- **Systems**: applications or services that perform actions, house logic, or provide user-facing capabilities. Examples: User Platform, Clinical Trial System, Order Service.
- **Stores**: persistent data assets. Examples: PostgreSQL database, S3 data lake, DynamoDB table, Snowflake warehouse.

**Important**: cloud data platforms such as Snowflake are Stores, NOT Systems, under the Sanofi framework.

### Store Placement Rules

Each Store belongs to the System that manages it:
- One System owns the data → Store is a container within that system
- Several Systems share a data asset (e.g., shared analytics database) → categorize under a **Shared Data Domain**

### Shared Data Domains

Several systems need the same data:
- Define domains at the **business/functional level**, never one global "shared data" bucket
- Examples: "R&D Shared Data", "Manufacturing Data", "Commercial Analytics"
- Each domain has clear ownership and access policies
- Show the domain boundary in the System Landscape diagram (systems and people only); model its Stores in the domain's own container view

### Mapping to C4

| Sanofi Concept | C4 Mapping |
|---------------|------------|
| System | Software System |
| Store (owned by one System) | Container (within that System) |
| Store (shared across Systems) | Container in the Shared Data Domain's own container view |
| Shared Data Domain | System boundary box in System Landscape diagram (no Stores inside) |
| External vendor platform | External Software System (grey) |

## Sources

- C4 model, Queues and topics: https://c4model.com/abstractions/queues-and-topics
- C4 model, Microservices: https://c4model.com/abstractions/microservices
