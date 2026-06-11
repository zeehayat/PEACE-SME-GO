package health

type DBStatus interface {
	Ping() error
}
type Handler struct {
	db DBStatus
}
