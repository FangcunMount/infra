package receipt

import (
	"os"
	"path/filepath"
	"testing"
)

func TestObservationRootMustBePrivateOwnedDirectoryAndNotSymlink(t *testing.T) {
	root := t.TempDir()
	if err := os.Chmod(root, 0700); err != nil {
		t.Fatal(err)
	}
	if !OwnedDirectory(root) {
		t.Fatal("owned private observation root rejected")
	}
	for _, path := range []string{"", ".", filepath.Join(root, "absent")} {
		if OwnedDirectory(path) {
			t.Fatal("nonexistent or relative observation root accepted")
		}
	}
	link := filepath.Join(root, "linked")
	if err := os.Symlink(root, link); err != nil {
		t.Fatal(err)
	}
	if OwnedDirectory(link) {
		t.Fatal("symlink observation directory accepted")
	}
	file := filepath.Join(root, "ordinary.json")
	if err := os.WriteFile(file, []byte("{}"), 0600); err != nil {
		t.Fatal(err)
	}
	if OwnedDirectory(file) {
		t.Fatal("ordinary file accepted as observation root")
	}
	if err := os.Chmod(root, 0755); err != nil {
		t.Fatal(err)
	}
	if OwnedDirectory(root) {
		t.Fatal("public observation root accepted")
	}
}
