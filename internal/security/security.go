package security

import "github.com/golang-jwt/jwt/v5"

// UserClaims models custom payload claims for JWT authentication.
type UserClaims struct {
	UserID int64 `json:"user_id"`
	jwt.RegisteredClaims
}

// AdminClaims models claims for administrative access.
type AdminClaims struct {
	Username   string `json:"admin_username"`
	Role       string `json:"role"`
	IsAdmin    bool   `json:"is_admin"`
	IsApprover bool   `json:"is_approver"`
	jwt.RegisteredClaims
}

// Identity matches the context object set by auth middlewares.
type Identity struct {
	UserID        int64
	AdminUsername string
	Role          string
	IsAdmin       bool
	IsApprover    bool
}
