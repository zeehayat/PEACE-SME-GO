package dto

// LoginRequest models incoming user credential JSON bodies.
type LoginRequest struct {
	Email    string `json:"email"`
	Password string `json:"password"`
}

// RegisterRequest models applicant signup registration requests.
type RegisterRequest struct {
	Email    string `json:"email"`
	Password string `json:"password"`
	CNIC     string `json:"cnic"`
	Name     string `json:"name"`
	Gender   string `json:"gender"`
}

// BusinessProfileRequest represents payloads to create/update business profiles.
type BusinessProfileRequest struct {
	NameOfBusiness                string   `json:"name_of_business"`
	BusinessRegistrationNumber    string   `json:"business_registration_number"`
	BusinessRegistrationAuthority []string `json:"business_registration_authority"`
	BusinessFullAddress           string   `json:"business_full_address"`
	BusinessLocationDistrict      string   `json:"business_location_district"`
	BusinessSector                string   `json:"business_sector"`
}

// GrantApplicationRequest models submitted grant details.
type GrantApplicationRequest struct {
	GrantRequired    float64 `json:"grant_required"`
	ContributionType string  `json:"contribution_type"`
	FinancialAmount  float64 `json:"financial_amount"`
	InKindDetails    string  `json:"inkind_details"`
}
