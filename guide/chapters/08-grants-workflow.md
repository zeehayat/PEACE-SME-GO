# Chapter 8: Grant Applications and Workflow Rules

## Purpose

The grant workflow is the core applicant feature. It teaches larger request payloads, JSONB fields, conditional validation, idempotent updates, and workflow gates. In this chapter, we will study **Interfaces**, understanding how Go implements structural typing (duck typing) without explicit declarations to write decoupled, testable code. We will then build a state machine workflow using interfaces.

This is where the project becomes a serious Go exercise. The request is large, the rules are conditional, the database stores nested JSONB data, and the workflow interacts with HFC background scoring.

---

## Foundational Concepts Explained Simply

### 1. Interfaces in Go
An **Interface** is a custom type that specifies a contract (a set of method signatures). Any struct that implements those exact methods automatically (implicitly) satisfies the interface.
- **No `implements` Keyword:** Unlike Java or C#, Go does not require you to declare that a struct implements an interface:
  - If it looks like a duck and quacks like a duck, it is a duck (**Duck Typing**).
  - This design decouples packages: you can define an interface locally in the package that *uses* it, rather than the package that *implements* it.
- **Polymorphism:** Allows you to swap out implementations (e.g. replacing a real database repo with a mock database repo in unit tests).

Here is a simple example:

```go
package main

import "fmt"

// Greeter interface requires a Greet method
type Greeter interface {
    Greet() string
}

// English speaker struct
type English struct{}
func (e English) Greet() string {
    return "Hello"
}

// Urdu speaker struct
type Urdu struct{}
func (u Urdu) Greet() string {
    return "السلام علیکم"
}

// SaySomething takes any type that satisfies Greeter interface
func SaySomething(g Greeter) {
    fmt.Println(g.Greet())
}

func main() {
    SaySomething(English{}) // Prints "Hello"
    SaySomething(Urdu{})    // Prints "السلام علیکم"
}
```

### 2. State Machine Rules
A State Machine maps out a set of distinct states and defines which state changes are valid. If a user tries to jump states illegally (e.g., transitioning directly from `Draft` to `Approved` without going through the `Submitted` stage), the state machine rejects the transition.

### External Resources
- [A Tour of Go: Interfaces](https://go.dev/tour/methods/9)
- [Effective Go: Interfaces and types](https://go.dev/doc/effective_go#interfaces_and_types)

---

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/grant` | Get current user's grant plus access state |
| POST | `/api/grant` | Create grant application |
| PUT | `/api/grant` | Update existing grant |
| GET | `/api/grant-status` | Show status, amount, and reason |

---

## Access Rule

If `GRANT_REQUIRE_SELECTION=1`, a user must have:

```sql
grant_access_whitelist.is_selected = TRUE
```

before posting a grant application.

`GET /api/grant` must include an `access_state` field so the frontend can show the right UI.

Application parallel:

- Admin uses `AdminUserAccess.vue` to set whitelist status.
- Applicant dashboard reads grant access state.
- Grant form unlocks only when selected.

Go concept: gate the write in the service, not only in Vue. Vue can hide the button, but Go must reject unauthorized submission.

---

## One Grant Per User

The schema enforces:

```sql
grants.user_id INTEGER UNIQUE NOT NULL
```

Use this as a design lesson:
- `POST` creates when no row exists.
- `PUT` updates an existing row.
- Duplicate creates should return a clear conflict or compatible error.

---

## Important Fields

Grant payload includes:
- `expression_of_interest`
- `grant_required`
- `working_capital`
- `financed_items`
- `contribution_type`
- `financial_amount`
- `inkind_details`
- `grant_support_growth`
- `job_creation_details`
- `domicile_district`
- `business_type`
- `tax_registration_status`
- `employment_grid`
- `declaration_accepted`
- `has_srsp_relative`
- `srsp_relatives`

Most array/object fields map naturally to PostgreSQL JSONB.

## Beginner Modeling Strategy

Do not start by writing one enormous handler. Model the request first:

```go
type GrantRequest struct {
    ExpressionOfInterest []string       `json:"expression_of_interest"`
    GrantRequired        float64        `json:"grant_required"`
    FinancedItems        []FinancedItem `json:"financed_items"`
    ContributionType     string         `json:"contribution_type"`
    HasSRSPRelative      bool           `json:"has_srsp_relative"`
    SRSPRelatives        []SRSPRelative `json:"srsp_relatives"`
}
```

Then write validation as a separate function. Then write the service. Then write the handler.

This order is easier to test:

```text
model -> validation -> service -> handler -> Vue
```

---

## Validation

Implement validation in layers:
- Required grant amount.
- Valid date format.
- `financed_items` rows have item, quantity, and cost.
- If contribution includes cash, require `financial_amount`.
- If contribution includes in-kind, require details and value.
- If `has_srsp_relative=true`, require at least one relative row.
- If `declaration_accepted=false`, reject final submission.

Application parallel: every conditional Vue section must have a matching backend validation rule. If Vue shows cash fields when contribution includes cash, Go must require cash amount when contribution includes cash.

| Vue condition | Go validation |
|---|---|
| contribution is cash | require `financial_amount` |
| contribution is in-kind | require `inkind_details` and `inkind_value` |
| relatives table shown | require at least one relative row |
| financed item added | require item name, quantity, cost |
| declaration checkbox | require `declaration_accepted=true` |

---

## HFC Hook

After grant create/update, enqueue HFC recalculation if `HFC_ASYNC_ENABLED=1`.

In early chapters, this can be a no-op interface:

```go
type HFCEnqueuer interface {
    EnqueueRecalculate(ctx context.Context, userID int64) error
}
```

Later chapters replace it with Redis-backed work.

Beginner rule: side effects should hide behind interfaces. Grant submission should not know whether HFC is implemented as a goroutine, Redis queue, or synchronous function.

---

## Practical Examples

### Example 1: Implementing a Type-Safe State Machine
This code defines the states of a grant application and writes a validation method to enforce strict transitions:

```go
// File: internal/grant/status.go
package grant

import "fmt"

type GrantStatus string

const (
	StatusDraft       GrantStatus = "Draft"
	StatusSubmitted   GrantStatus = "Submitted"
	StatusUnderReview GrantStatus = "Under Review"
	StatusApproved    GrantStatus = "Approved"
	StatusRejected    GrantStatus = "Rejected"
)

// CanTransitionTo returns an error if the state change is invalid.
func (current GrantStatus) CanTransitionTo(next GrantStatus) error {
	switch current {
	case StatusDraft:
		if next == StatusSubmitted {
			return nil
		}
	case StatusSubmitted:
		if next == StatusUnderReview || next == StatusApproved || next == StatusRejected {
			return nil
		}
	case StatusUnderReview:
		if next == StatusApproved || next == StatusRejected {
			return nil
		}
	case StatusApproved, StatusRejected:
		return fmt.Errorf("cannot transition away from terminal state %q to %q", current, next)
	default:
		return fmt.Errorf("unsupported source state %q", current)
	}

	return fmt.Errorf("state transition from %q to %q is disallowed", current, next)
}
```

### Example 2: Interfaced Workflow Decoupling
This service layer demonstrates how interfaces allow us to process a grant submission and enqueue background scoring without coupling the code directly to specific databases or queue mechanisms:

```go
// File: internal/grant/service.go
package grant

import (
	"context"
	"fmt"
)

// GrantRepository defines database behaviors needed by this service.
type GrantRepository interface {
	GetStatus(ctx context.Context, userID int64) (GrantStatus, error)
	UpdateStatus(ctx context.Context, userID int64, newStatus GrantStatus) error
}

// HFCEnqueuer defines queue behaviors needed by this service.
type HFCEnqueuer interface {
	EnqueueRecalculate(ctx context.Context, userID int64) error
}

type WorkflowService struct {
	repo   GrantRepository
	hfcSvc HFCEnqueuer
}

// NewWorkflowService injects dynamic implementations satisfying the interfaces.
func NewWorkflowService(repo GrantRepository, hfcSvc HFCEnqueuer) *WorkflowService {
	return &WorkflowService{
		repo:   repo,
		hfcSvc: hfcSvc,
	}
}

func (s *WorkflowService) SubmitGrant(ctx context.Context, userID int64) error {
	currentStatus, err := s.repo.GetStatus(ctx, userID)
	if err != nil {
		return fmt.Errorf("failed to fetch grant status: %w", err)
	}

	// 1. Enforce state machine rules
	if err := currentStatus.CanTransitionTo(StatusSubmitted); err != nil {
		return err
	}

	// 2. Perform DB write
	if err := s.repo.UpdateStatus(ctx, userID, StatusSubmitted); err != nil {
		return fmt.Errorf("failed to write status: %w", err)
	}

	// 3. Trigger async scoring side-effect via interface
	if err := s.hfcSvc.EnqueueRecalculate(ctx, userID); err != nil {
		fmt.Printf("Warning: failed to enqueue HFC job: %v\n", err)
	}

	return nil
}
```

---

## Mastery Check

You understand this chapter when you can:
- Explain what implicit interface implementation means in Go.
- Create an interface and write structs that satisfy it.
- Explain how interfaces decouple packages.
- Implement state transition rules in a custom state machine.
