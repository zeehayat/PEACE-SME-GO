package db

import (
	"database/sql"
	"encoding/json"
	"time"
)

type User struct {
	UserID            int64          `json:"user_id"`
	EmailAddress      string         `json:"email_address"`
	HashedPassword    string         `json:"-"`
	FirstName         sql.NullString `json:"first_name"`
	LastName          sql.NullString `json:"last_name"`
	MiddleName        sql.NullString `json:"middle_name"`
	CNIC              sql.NullString `json:"cnic"`
	Language          sql.NullString `json:"language"`
	Gender            sql.NullString `json:"gender"`
	MobileNo          sql.NullString `json:"mobile_no"`
	WhatsappNo        sql.NullString `json:"whatsapp_no"`
	TermsAccepted     bool           `json:"terms_accepted"`
	Status            string         `json:"status"`
	LastLoginIP       sql.NullString `json:"last_login_ip"`
	DeviceFingerPrint sql.NullString `json:"device_fingerprint"`
	CreatedAt         sql.NullTime   `json:"created_at"`
}
type Business struct {
	BusinessID                    int64           `json:"business_id"`
	UserID                        int64           `json:"user_id"`
	NameOfBusiness                sql.NullString  `json:"name_of_business"`
	BusinessRegistrationNumber    sql.NullString  `json:"business_registration_number"`
	BusinessRegistrationDate      sql.NullTime    `json:"business_registration_date"`
	BusinessRegistrationAuthority json.RawMessage `json:"business_registration_authority"`
	OtherAuthorityText            sql.NullString  `json:"other_authority_text"`
	BusinessFullAddress           sql.NullString  `json:"business_full_address"`
	SocialMediaPage               sql.NullString  `json:"social_media_page"`
	SocialMediaPage2              sql.NullString  `json:"social_media_page_2"`
	SocialMediaPage3              sql.NullString  `json:"social_media_page_3"`
	SocialMediaPage4              sql.NullString  `json:"social_media_page_4"`
	MaleEmployees                 sql.NullInt64   `json:"male_employees"`
	FemaleEmployees               sql.NullInt64   `json:"female_employees"`
	BusinessLocationDistrict      sql.NullString  `json:"business_location_district"`
	BusinessSector                sql.NullString  `json:"business_sector"`
	HowDidYouHear                 sql.NullString  `json:"how_did_you_hear"`
	HasSRSPRelation               bool            `json:"has_srsp_relation"`
	SRSPRelativesData             json.RawMessage `json:"srsp_relatives_data"` // JSONB Array
	CreatedAt                     time.Time       `json:"created_at"`
}

type BusinessDocument struct {
	DocumentID   int64     `json:"document_id"`
	BusinessID   int64     `json:"business_id"`
	DocumentType string    `json:"document_type"`
	FileName     string    `json:"file_name"`
	FilePath     string    `json:"file_path"` // Public S3 URL
	MIMEType     string    `json:"mime_type"`
	CreatedAt    time.Time `json:"created_at"`
}

type FinancedItem struct {
	Item          string  `json:"item"`
	Quantity      int     `json:"quantity"`
	EstimatedCost float64 `json:"estimated_cost"`
}
type SRSPRelative struct {
	Name     string `json:"name"`
	Position string `json:"position"`
	Office   string `json:"office"`
}
type Grant struct {
	GrantID                 int64           `json:"grant_id"`
	UserID                  int64           `json:"user_id"`
	ExpressionOfInterest    sql.NullString  `json:"expression_of_interest"` // JSON string
	GrantRequired           sql.NullFloat64 `json:"grant_required"`
	ApplicationDate         sql.NullTime    `json:"application_date"`
	Status                  string          `json:"status"` // 'Pending', 'Approved', etc.
	ContributionType        sql.NullString  `json:"contribution_type"`
	FinancialAmount         sql.NullFloat64 `json:"financial_amount"`
	FinancialAmountWords    sql.NullString  `json:"financial_amount_words"`
	InKindDetails           sql.NullString  `json:"inkind_details"`
	InKindValue             sql.NullFloat64 `json:"inkind_value"`
	ContributionUtilization sql.NullString  `json:"contribution_utilization"`
	GrantSupportGrowth      sql.NullString  `json:"grant_support_growth"`
	JobCreationDetails      sql.NullString  `json:"job_creation_details"`
	GrantAmountWords        sql.NullString  `json:"grant_amount_words"`
	OtherPurposeText        sql.NullString  `json:"other_purpose_text"`
	HowDidYouHear           sql.NullString  `json:"how_did_you_hear"`
	ApprovedAmount          sql.NullFloat64 `json:"approved_amount"`
	ApprovalReason          sql.NullString  `json:"approval_reason"`
	ApprovedAt              sql.NullTime    `json:"approved_at"`
	ApprovedBy              sql.NullString  `json:"approved_by"`
	HFCStatus               string          `json:"hfc_status"` // 'HFC_Pending', 'Clear', etc.
	HFCScore                int             `json:"hfc_score"`
	HFCRiskLevel            string          `json:"hfc_risk_level"`
	HFCLastEvaluatedAt      sql.NullTime    `json:"hfc_last_evaluated_at"`
	HFCModelVersion         sql.NullString  `json:"hfc_model_version"`
	DomicileDistrict        sql.NullString  `json:"domicile_district"`
	BusinessType            json.RawMessage `json:"business_type"`
	BusinessTypeOther       sql.NullString  `json:"business_type_other"`
	TaxRegistrationStatus   json.RawMessage `json:"tax_registration_status"`
	NTNRegistrationNo       sql.NullString  `json:"ntn_registration_no"`
	TaxFilerStatus          sql.NullString  `json:"tax_filer_status"`
	WorkingCapital          bool            `json:"working_capital"`
	FinancedItems           json.RawMessage `json:"financed_items"` // Scans nested

	ExpectedProductionIncrease sql.NullString  `json:"expected_production_increase"`
	EmploymentGrid             json.RawMessage `json:"employment_grid"`
	DeclarationAccepted        bool            `json:"declaration_accepted"`
	DeclarationName            sql.NullString  `json:"declaration_name"`
	HasSRSPRelative            bool            `json:"has_srsp_relative"`
	SRSPRelatives              json.RawMessage `json:"srsp_relatives"` // Scans nested

}
type HFCEvaluation struct {
	EvaluationID int64     `json:"evaluation_id"`
	UserID       int64     `json:"user_id"`
	Score        int       `json:"score"`
	RiskLevel    string    `json:"risk_level"`
	RuleDetails  string    `json:"rule_details"` // JSON string breakdown
	EvaluatedAt  time.Time `json:"evaluated_at"`
}
