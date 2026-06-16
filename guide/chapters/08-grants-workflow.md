# Chapter 8: Grant Applications and Workflow Rules

## Purpose

The grant workflow is the core applicant feature. It teaches larger request payloads, JSONB fields, conditional validation, idempotent updates, and workflow gates. In this chapter, we will study **Interfaces**, understanding how Go implements structural typing (duck typing) without explicit declarations. We will then define **all key application interfaces** used to decouple layers and enable unit testing fakes.

---

## Foundational Concepts Explained Simply

### 1. Interfaces in Go

:::expandable [Go Interfaces & Implicit Implementation]
#### In-Depth Explanation
An **Interface** in Go is a type that declares a contract composed of one or more method signatures.
* **No `implements` Keyword:** Unlike Java, C#, or TypeScript, you do not explicitly declare that a struct implements an interface.
* **Implicit Satisfaction (Duck Typing):** If a concrete type (like a struct) defines all the methods that an interface requires (with matching names, parameters, and return types), the Go compiler automatically allows that struct to be used wherever that interface is expected.
* **Why This is Powerful:** 
  1. **Decoupling:** High-level packages can declare interfaces outlining *only* the specific operations they need, rather than importing thick implementation details from lower-level packages.
  2. **Unit Testing:** You can easily swap real infrastructure implementations (like an S3 uploader or a PostgreSQL database connection) with lightweight, local testing fakes (mocks) in your test files by simply satisfying the interface methods.

#### Sandbox Program: Mocking an Email Client via Interfaces
This sandbox shows how an HTTP service can call an email notifier interface, allowing us to pass a production SMTP client or a local mock tester for unit testing without changing the service code:

```go
package main

import (
	"fmt"
)

// Notifier defines the communication contract
type Notifier interface {
	SendEmail(recipient string, body string) error
}

// ProductionEmailService connects to an external SMTP server
type ProductionEmailService struct {
	APIKey string
}

func (p ProductionEmailService) SendEmail(recipient string, body string) error {
	fmt.Printf("[PROD SMTP] Sending network packet to %s using Brevo Key...\n", recipient)
	return nil
}

// MockEmailService records inputs in-memory for unit testing (no network activity)
type MockEmailService struct {
	SentEmails map[string]string
}

func (m *MockEmailService) SendEmail(recipient string, body string) error {
	m.SentEmails[recipient] = body
	fmt.Printf("[MOCK MAIL] Appended message in memory for %s\n", recipient)
	return nil
}

// NotificationDispatcher depends on the Notifier interface, NOT concrete types
type NotificationDispatcher struct {
	MailClient Notifier
}

func (nd NotificationDispatcher) WelcomeUser(email string) {
	_ = nd.MailClient.SendEmail(email, "Welcome to the PEACE SME Portal!")
}

func main() {
	// 1. Simulate Production Execution
	prodService := ProductionEmailService{APIKey: "sk_brevo_998877"}
	prodDispatcher := NotificationDispatcher{MailClient: prodService}
	prodDispatcher.WelcomeUser("applicant@swat.org")

	fmt.Println()

	// 2. Simulate Unit Test Execution
	mockService := &MockEmailService{SentEmails: make(map[string]string)}
	testDispatcher := NotificationDispatcher{MailClient: mockService}
	testDispatcher.WelcomeUser("test-applicant@shangla.org")

	// Verify the mock state to confirm email was "sent" during assertions
	fmt.Printf("Mock Registry State: Verified sent welcome mail to %s -> %q\n", 
		"test-applicant@shangla.org", mockService.SentEmails["test-applicant@shangla.org"])
}
```
:::

### External Resources
- [A Tour of Go: Interfaces](https://go.dev/tour/methods/9)
- [Effective Go: Interfaces and types](https://go.dev/doc/effective_go#interfaces_and_types)

---

## Phased Interfaces Implementation Guide

To master decoupling, we will now define **all core repository and service interfaces** required to run the PEACE SME Grant Portal.

Create a file named [internal/domain/interfaces.go](file:///var/www/peace-sme-go/internal/domain/interfaces.go) to declare these interfaces.

### 1. Repository Interfaces
These define operations performed against our PostgreSQL data layer:

```go
package domain

import (
	"context"
	"peace-sme-go/internal/db"
)

// UserRepository handles user entity retrieval and updates.
type UserRepository interface {
	FindByID(ctx context.Context, userID int64) (*db.User, error)
	FindByEmail(ctx context.Context, email string) (*db.User, error)
	Create(ctx context.Context, user *db.User) error
	UpdateStatus(ctx context.Context, userID int64, status string) error
}

// BusinessRepository handles business entity operations.
type BusinessRepository interface {
	FindByUserID(ctx context.Context, userID int64) (*db.Business, error)
	Create(ctx context.Context, biz *db.Business) error
	Update(ctx context.Context, biz *db.Business) error
}

// GrantRepository manages grant workflow operations.
type GrantRepository interface {
	FindByUserID(ctx context.Context, userID int64) (*db.Grant, error)
	Create(ctx context.Context, grant *db.Grant) error
	Update(ctx context.Context, grant *db.Grant) error
	UpdateStatus(ctx context.Context, userID int64, status string) error
	GetStatus(ctx context.Context, userID int64) (string, error)
}
```

### 2. Infrastructure Service Interfaces
These interfaces decouple our business rules from third-party systems like Redis, S3 storage, and email REST clients:

```go
// HFCEnqueuer enqueues asynchronous fraud scoring evaluations.
type HFCEnqueuer interface {
	EnqueueRecalculate(ctx context.Context, userID int64) error
}

// MailService handles asynchronous email alerts.
type MailService interface {
	SendWelcomeEmail(ctx context.Context, toEmail string, name string) error
	SendGrantApprovedEmail(ctx context.Context, toEmail string, approvedAmount float64) error
}

// StorageClient generates upload links and manages asset deletion on S3.
type StorageClient interface {
	GeneratePresignedPutURL(ctx context.Context, objectKey string, contentType string) (string, error)
	DeleteObject(ctx context.Context, objectURL string) error
}
```

---

## State Machine Rules

A State Machine enforces valid workflow state changes. In Go, represent this logic as checking current states against target states:

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
		return fmt.Errorf("cannot modify status once in terminal state %q", current)
	}
	return fmt.Errorf("illegal state transition from %q to %q", current, next)
}
```

---

## Practical Examples

### Example: Decoupled Workflow Execution using Interfaces
This service transitions a grant application to `Submitted` and enqueues background HFC scoring using injected interface objects:

```go
// File: internal/grant/service.go
package grant

import (
	"context"
	"fmt"
	"peace-sme-go/internal/domain"
)

type Service struct {
	repo   domain.GrantRepository
	hfcSvc domain.HFCEnqueuer
}

func NewService(repo domain.GrantRepository, hfcSvc domain.HFCEnqueuer) *Service {
	return &Service{
		repo:   repo,
		hfcSvc: hfcSvc,
	}
}

func (s *Service) Submit(ctx context.Context, userID int64) error {
	statusStr, err := s.repo.GetStatus(ctx, userID)
	if err != nil {
		return fmt.Errorf("failed to retrieve status: %w", err)
	}

	current := GrantStatus(statusStr)
	if err := current.CanTransitionTo(StatusSubmitted); err != nil {
		return err
	}

	if err := s.repo.UpdateStatus(ctx, userID, string(StatusSubmitted)); err != nil {
		return fmt.Errorf("failed to update status: %w", err)
	}

	// Trigger async scoring via the decoupled interface
	if err := s.hfcSvc.EnqueueRecalculate(ctx, userID); err != nil {
		// Log warning but don't fail user request
		fmt.Printf("Warning: failed to enqueue HFC job: %v\n", err)
	}

	return nil
}
```

---

## Mastery Check

You understand this chapter when you can:
- Explain Go's implicit satisfaction rule and how it differs from explicit implementation models.
- Declare a clean interface and implement a mock structure that satisfies it.
- Use interface injection to decouple handlers and service layers.
- Build state transition checks enforcing strict workflow rules.
