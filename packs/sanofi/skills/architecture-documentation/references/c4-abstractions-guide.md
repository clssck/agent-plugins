# C4 Abstractions Guide

Definitions, boundary rules, and common mistakes for the four C4 model abstractions.
Use this reference to correctly classify elements when building C4 diagrams.

## Table of Contents

- [Person](#person)
- [Software System](#software-system)
- [Container](#container)
  - [What IS a Container](#what-is-a-container)
  - [What IS NOT a Container](#what-is-not-a-container)
  - [Key Rules](#key-rules)
- [Component](#component)
- [Common Mistakes](#common-mistakes)
- [Sanofi Modeling Framework](#sanofi-modeling-framework)
  - [Systems vs. Stores](#systems-vs-stores)
  - [Store Placement Rules](#store-placement-rules)
  - [Shared Data Domains](#shared-data-domains)
  - [Mapping to C4](#mapping-to-c4)

---

## Person

**Definition**: A human user of the software system. Represents the human actors who
interact directly with the system.

**When to use roles vs. named individuals:**
- Use **roles** in most diagrams (e.g., "Pharmacist", "Administrator", "Patient")
- Use **named individuals** only in team-specific deployment or org-chart diagrams
- Multiple roles can interact with the same system in different ways

**Naming conventions:**
- Format: `[Role] [Optional: Organization/Context]`
- Examples: `Pharmacist (Retail)`, `Clinical Trial Manager`, `Data Analyst`, `External Auditor`
- Keep names short but specific enough to distinguish roles

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

**Definition**: The highest level of abstraction in C4. A software system is something
that delivers value to its users, whether human or automated. It is the overall
"application" or "product" being documented.

**Scope evidence (not fixed rules):**
- A software system has a clear business purpose, users, and boundary that is useful
  to the audience of the diagram.
- Team ownership, repository layout, deployment topology, and release cadence are
  useful evidence, but none alone defines a system boundary.
- One repository can contain several systems; one system can span several repositories
  or teams.

**Boundary questions:**
- **User-facing purpose**: Does the candidate deliver a distinct capability or value
  proposition to users or other systems?
- **Lifecycle and governance**: Is it planned, operated, secured, and changed as a
  coherent product/application boundary?
- **Relationship clarity**: Would modeling it separately make its dependencies and
  responsibilities clearer to the intended audience?

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

These are organizational or strategic concepts, not software systems. A software system
is a concrete thing that a team builds, deploys, and maintains.

**In-scope vs. external:**
- The system under documentation is shown in **blue** (#0047BB) at the center
- External systems (other teams' systems, third-party services) are shown in **grey** (#6D6E71)
- An "external" system is anything outside the documented software-system boundary,
  regardless of team ownership

**Naming convention:** `[Product Name] System`
Examples: `User Platform System`, `Clinical Trial Management System`, `Order Processing System`

---

## Container

**Definition**: An application or data store that needs to be running for the overall
system to work. A container is a **separately runnable/deployable unit** that executes
code or stores data. Think of it as a runtime process boundary.

**IMPORTANT**: "Container" in C4 does NOT mean "Docker container." A Docker container
is a deployment mechanism; a C4 container is an architectural abstraction.

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
A browser SPA is normally a client-side container. Model an API, asset host, or other
server-side runtime as an additional container only when it is a distinct in-scope
runtime or data-store responsibility. The API may serve the SPA assets, be deployed
separately, or be external to the documented system; do not infer a second container
solely from the presence of a frontend repository or development server.

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
Model a managed cloud service as a container when it is within the documented system
boundary and its data-store or runtime responsibility matters to the view. Model it as
an external system when the system merely consumes it, or omit it when including it
would not help the intended audience. Ownership and provisioning are evidence, not an
automatic classification.

**Single deployment, multiple containers:**
Do not collapse distinct runtime or data-store responsibilities solely because local
development starts them together. Conversely, do not split implementation details that
do not have independently meaningful runtime responsibilities. Put deployment topology
in Deployment diagrams.

**Queues, topics, and message buses:**
Model each queue or topic you own as a data-store container. NEVER model the message
broker itself (Kafka cluster, RabbitMQ server) as one hub container: a hub hides
producer-consumer coupling. Alternatively omit the queues and put the queue name in the
relationship label ("Sends order events via `orders-queue` to"). Either is valid; keep one
choice per diagram set. The broker or cluster belongs on the Deployment diagram. When services are
separate software systems, a shared queue needs a stated owner (the producer, the consumer, or
a third party).

**Microservices:**
Inside one team's single software system, each microservice is a group of one or more
containers (API plus its data store); show them as containers within one system boundary.
Promote a service to its own software system only when a separate team owns and operates it.

---

## Component

**Definition**: A grouping of related functionality encapsulated behind a well-defined
interface. Components live inside a container and are NOT separately deployable.

**Grouping strategies:**
- **Layered**: Controllers, Services, Repositories, Middleware
- **Feature/domain**: UserModule, OrderModule, PaymentModule
- **Hexagonal**: Adapters (driving/driven), Application Services, Domain Services
- **Hybrid**: Group by architectural significance, using whatever organization
  best communicates the container's internal structure

**Hexagonal architecture note on Ports:**
Ports (inbound and outbound) are **interfaces/contracts**, not architectural components.
They define what a container offers (inbound) and what it requires (outbound). Do NOT
model ports as separate components in L3 diagrams. Instead, document ports as **notes on
the container** in L2 diagrams (e.g., a diagram note listing "Inbound: REST API, Event
Listener" and "Outbound: Database, Message Queue"). The actual C4 components in a
hexagonal codebase are the **Adapters** (implementations) and **Services** (use cases,
domain logic).

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
1. Identify the major responsibilities of the container
2. Group related code elements by those responsibilities
3. Define clear interfaces between groups
4. Exclude noise: data models, utilities, config, constants
5. Include only the responsibilities needed to explain the container to the intended
   audience; C4 has no fixed component-count target.
6. Split, regroup, or omit detail when the view becomes hard to read or stops answering
   a useful architectural question.

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
| Mixing abstraction levels | Having both systems and components in one diagram | Each diagram should be one C4 level |
| Bidirectional arrows | C4 uses unidirectional relationships | Two separate arrows if communication goes both ways |
| Person interacting with database directly | Users interact with applications, not databases | Route through the application container |
| Modeling tools/frameworks as elements | Frameworks are technology choices, not architectural units | Annotate as [Technology] label or comment on the element that uses them |
| Modeling each Lambda as a container | Multiple Lambdas behind one API Gateway are one service | Consolidate into one container (see Serverless Consolidation Pattern) |
| Treating every managed service as a container or as external | Classification follows scope and responsibility, not provisioning | Apply the managed-cloud-service rule; your Lambda action groups are containers either way |

---

## Sanofi Modeling Framework

### Systems vs. Stores

Sanofi's architecture governance distinguishes:

- **Systems** = applications or services that perform actions, house logic, or provide
  user-facing capabilities. Examples: User Platform, Clinical Trial System, Order Service.
- **Stores** = persistent data assets. Examples: PostgreSQL database, S3 data lake,
  DynamoDB table, Snowflake warehouse.

**Important**: Cloud data platforms like Snowflake are NOT classified as Systems under
the Sanofi framework. They are Stores.

### Store Placement Rules

Each Store is associated with the System that manages it:
- If one System owns the data, place the Store as a container within that system
- If multiple Systems share a data asset (e.g., a shared analytics database), categorize
  it under a **Shared Data Domain**

### Shared Data Domains

When multiple systems need access to the same data:
- Define domains at the **business/functional level** (not a single global "shared data" bucket)
- Examples: "R&D Shared Data", "Manufacturing Data", "Commercial Analytics"
- Each domain has clear ownership and access policies
- Document in the System Landscape diagram

### Mapping to C4

| Sanofi Concept | C4 Mapping |
|---------------|------------|
| System | Software System |
| Store (owned by one System) | Container (within that System) |
| Store (shared across Systems) | Container in Shared Data Domain boundary |
| Shared Data Domain | System boundary box (in System Landscape diagram) |
| External vendor platform | External Software System (grey) |

## Sources

- C4 model, Queues and topics: https://c4model.com/abstractions/queues-and-topics
- C4 model, Microservices: https://c4model.com/abstractions/microservices
