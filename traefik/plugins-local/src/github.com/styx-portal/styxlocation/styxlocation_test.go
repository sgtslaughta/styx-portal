package styxlocation_test

import (
	"bufio"
	"context"
	"net"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/styx-portal/styxlocation"
)

func handler(t *testing.T, host string, next http.Handler) http.Handler {
	t.Helper()
	cfg := styxlocation.CreateConfig()
	cfg.Host = host
	h, err := styxlocation.New(context.Background(), next, cfg, "test")
	if err != nil {
		t.Fatal(err)
	}
	return h
}

func redirect(header, value string) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set(header, value)
		w.WriteHeader(http.StatusFound)
	})
}

func TestLocation(t *testing.T) {
	cases := []struct{ name, in, want string }{
		{"https", "https://app.example.lan/login", "/login"},
		{"http", "http://app.example.lan/login", "/login"},
		{"port", "https://app.example.lan:8443/login", "/login"},
		{"uppercase", "https://APP.Example.LAN/login", "/login"},
		{"scheme-relative", "//app.example.lan/login", "/login"},
		{"query+fragment", "https://app.example.lan/a/b?x=1&y=2#frag", "/a/b?x=1&y=2#frag"},
		{"empty path", "https://app.example.lan", "/"},
		{"empty path with query", "https://app.example.lan?x=1", "/?x=1"},
		{"other host", "https://other.example.lan/login", "https://other.example.lan/login"},
		{"suffix host", "https://evil-app.example.lan/x", "https://evil-app.example.lan/x"},
		{"relative", "/login?x=1", "/login?x=1"},
		{"relative no slash", "login", "login"},
		{"unparsable", "http://[::1/x", "http://[::1/x"},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			rec := httptest.NewRecorder()
			handler(t, "app.example.lan", redirect("Location", c.in)).
				ServeHTTP(rec, httptest.NewRequest("GET", "/", nil))
			if got := rec.Header().Get("Location"); got != c.want {
				t.Fatalf("got %q want %q", got, c.want)
			}
			if rec.Code != http.StatusFound {
				t.Fatalf("status %d", rec.Code)
			}
		})
	}
}

func TestHostConfigIsCaseInsensitive(t *testing.T) {
	rec := httptest.NewRecorder()
	handler(t, "App.Example.LAN", redirect("Location", "https://app.example.lan/x")).
		ServeHTTP(rec, httptest.NewRequest("GET", "/", nil))
	if got := rec.Header().Get("Location"); got != "/x" {
		t.Fatalf("got %q", got)
	}
}

func TestRefresh(t *testing.T) {
	cases := []struct{ in, want string }{
		{"0; url=https://app.example.lan/x?a=1", "0; url=/x?a=1"},
		{"5;URL=http://app.example.lan:81/x", "5;URL=/x"},
		{"0; url=https://other.lan/x", "0; url=https://other.lan/x"},
		{"3", "3"},
		{"0; url=/x", "0; url=/x"},
	}
	for _, c := range cases {
		rec := httptest.NewRecorder()
		handler(t, "app.example.lan", redirect("Refresh", c.in)).
			ServeHTTP(rec, httptest.NewRequest("GET", "/", nil))
		if got := rec.Header().Get("Refresh"); got != c.want {
			t.Fatalf("in %q got %q want %q", c.in, got, c.want)
		}
	}
}

func TestNoLocationUntouched(t *testing.T) {
	rec := httptest.NewRecorder()
	handler(t, "app.example.lan", http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("X-A", "b")
		_, _ = w.Write([]byte("body https://app.example.lan/x"))
	})).ServeHTTP(rec, httptest.NewRequest("GET", "/", nil))
	if rec.Header().Get("Location") != "" || rec.Header().Get("X-A") != "b" ||
		rec.Body.String() != "body https://app.example.lan/x" {
		t.Fatalf("modified: %v %q", rec.Header(), rec.Body.String())
	}
}

func TestWriteWithoutWriteHeader(t *testing.T) {
	rec := httptest.NewRecorder()
	handler(t, "app.example.lan", http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Location", "https://app.example.lan/x")
		_, _ = w.Write([]byte("hi"))
	})).ServeHTTP(rec, httptest.NewRequest("GET", "/", nil))
	if got := rec.Header().Get("Location"); got != "/x" {
		t.Fatalf("got %q", got)
	}
	if rec.Body.String() != "hi" {
		t.Fatalf("body %q", rec.Body.String())
	}
}

func TestEmptyHostErrors(t *testing.T) {
	_, err := styxlocation.New(context.Background(), http.NotFoundHandler(),
		styxlocation.CreateConfig(), "x")
	if err == nil {
		t.Fatal("expected error")
	}
}

type fake struct {
	*httptest.ResponseRecorder
	flushed, hijacked bool
}

func (f *fake) Flush() { f.flushed = true }
func (f *fake) Hijack() (net.Conn, *bufio.ReadWriter, error) {
	f.hijacked = true
	return nil, nil, nil
}

func TestFlushAndHijackPassThrough(t *testing.T) {
	f := &fake{ResponseRecorder: httptest.NewRecorder()}
	handler(t, "app.example.lan", http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		fl, ok := w.(http.Flusher)
		if !ok {
			t.Error("no Flusher")
		} else {
			fl.Flush()
		}
		hj, ok := w.(http.Hijacker)
		if !ok {
			t.Error("no Hijacker")
		} else if _, _, err := hj.Hijack(); err != nil {
			t.Error(err)
		}
	})).ServeHTTP(f, httptest.NewRequest("GET", "/", nil))
	if !f.flushed || !f.hijacked {
		t.Fatalf("flushed=%v hijacked=%v", f.flushed, f.hijacked)
	}
}

func TestHijackUnsupported(t *testing.T) {
	rec := httptest.NewRecorder() // not a Hijacker
	handler(t, "app.example.lan", http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if _, _, err := w.(http.Hijacker).Hijack(); err == nil {
			t.Error("expected error")
		}
	})).ServeHTTP(rec, httptest.NewRequest("GET", "/", nil))
}
