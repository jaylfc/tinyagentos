import { useState } from "react";
import { ChevronLeft, Plus, Search, Trash2, User } from "lucide-react";
import { Button, Input, Textarea, Label } from "@/components/ui";

interface Contact {
  id: string;
  name: string;
  email: string;
  phone: string;
  notes: string;
}

function newId() {
  return Math.random().toString(36).slice(2, 10);
}

const emptyContact = (): Contact => ({
  id: newId(),
  name: "",
  email: "",
  phone: "",
  notes: "",
});

export function ContactsApp({ windowId: _windowId }: { windowId: string }) {
  const [contacts, setContacts] = useState<Contact[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [editing, setEditing] = useState<Contact | null>(null);
  const [search, setSearch] = useState("");

  const filtered = contacts.filter(
    (c) =>
      c.name.toLowerCase().includes(search.toLowerCase()) ||
      c.email.toLowerCase().includes(search.toLowerCase()) ||
      c.phone.includes(search)
  );

  const selected = contacts.find((c) => c.id === selectedId) ?? null;

  function handleAdd() {
    const c = emptyContact();
    setEditing(c);
    setSelectedId(null);
  }

  function handleSave() {
    if (!editing) return;
    if (!editing.name.trim()) return;
    setContacts((prev) => {
      const idx = prev.findIndex((c) => c.id === editing.id);
      if (idx >= 0) {
        const next = [...prev];
        next[idx] = editing;
        return next;
      }
      return [...prev, editing];
    });
    setSelectedId(editing.id);
    setEditing(null);
  }

  function handleDelete(id: string) {
    setContacts((prev) => prev.filter((c) => c.id !== id));
    if (selectedId === id) setSelectedId(null);
    if (editing?.id === id) setEditing(null);
  }

  function handleEdit() {
    if (selected) setEditing({ ...selected });
  }

  function handleCancel() {
    setEditing(null);
  }

  const isMobile = typeof window !== "undefined" && window.innerWidth < 640;
  const showDetailOnly = isMobile && (editing !== null || selectedId !== null);
  const showListOnly = isMobile && !showDetailOnly;

  return (
    <div className="flex h-full bg-shell-bg-deep text-shell-text select-none">
      {/* Sidebar */}
      <div
        className={
          isMobile
            ? showListOnly
              ? "w-full flex flex-col"
              : "hidden"
            : "w-56 shrink-0 flex flex-col border-r border-white/5"
        }
      >
        {/* Search + Add */}
        <div className="p-3 flex gap-2">
          <div className="relative flex-1">
            <Search
              size={14}
              className="absolute left-2.5 top-1/2 -translate-y-1/2 text-shell-text-tertiary pointer-events-none z-10"
            />
            <Input
              type="text"
              placeholder="Search…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="pl-8 h-8"
              aria-label="Search contacts"
            />
          </div>
          <Button
            variant="ghost"
            size="icon"
            onClick={handleAdd}
            className="shrink-0 h-8 w-8"
            aria-label="Add contact"
          >
            <Plus size={16} />
          </Button>
        </div>

        {/* Contact list */}
        <div className="flex-1 overflow-y-auto">
          {filtered.length === 0 && (
            <p className="text-shell-text-tertiary text-xs text-center mt-8">
              {contacts.length === 0 ? "No contacts yet" : "No results"}
            </p>
          )}
          {filtered.map((c) => (
            <Button
              key={c.id}
              variant={selectedId === c.id ? "secondary" : "ghost"}
              onClick={() => {
                setSelectedId(c.id);
                setEditing(null);
              }}
              className="w-full justify-start h-auto py-2.5 px-3 rounded-none font-normal"
              aria-label={`Select ${c.name}`}
            >
              <div className="w-8 h-8 rounded-full bg-shell-surface flex items-center justify-center shrink-0">
                <User size={14} className="text-shell-text-secondary" />
              </div>
              <div className="min-w-0 flex-1 text-left">
                <div className="text-sm font-medium truncate">{c.name}</div>
                {c.email && (
                  <div className="text-xs text-shell-text-secondary truncate">
                    {c.email}
                  </div>
                )}
              </div>
            </Button>
          ))}
        </div>
      </div>

      {/* Detail panel */}
      <div
        className={
          isMobile
            ? showDetailOnly
              ? "w-full flex flex-col overflow-y-auto"
              : "hidden"
            : "flex-1 flex flex-col overflow-y-auto"
        }
      >
        {isMobile && showDetailOnly && (
          <div className="px-3 py-2 border-b border-white/5 shrink-0">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => {
                setEditing(null);
                setSelectedId(null);
              }}
              aria-label="Back to contacts"
              className="h-7"
            >
              <ChevronLeft size={14} />
              Contacts
            </Button>
          </div>
        )}
        {editing ? (
          <div className="p-6 flex flex-col gap-4 max-w-md">
            <h2 className="text-lg font-semibold">
              {contacts.find((c) => c.id === editing.id)
                ? "Edit Contact"
                : "New Contact"}
            </h2>
            <div className="flex flex-col gap-1">
              <Label htmlFor="contact-name">Name</Label>
              <Input
                id="contact-name"
                value={editing.name}
                onChange={(e) =>
                  setEditing({ ...editing, name: e.target.value })
                }
                placeholder="Full name"
                aria-label="Name"
                autoFocus
              />
            </div>
            <div className="flex flex-col gap-1">
              <Label htmlFor="contact-email">Email</Label>
              <Input
                id="contact-email"
                value={editing.email}
                onChange={(e) =>
                  setEditing({ ...editing, email: e.target.value })
                }
                placeholder="email@example.com"
                aria-label="Email"
              />
            </div>
            <div className="flex flex-col gap-1">
              <Label htmlFor="contact-phone">Phone</Label>
              <Input
                id="contact-phone"
                value={editing.phone}
                onChange={(e) =>
                  setEditing({ ...editing, phone: e.target.value })
                }
                placeholder="+1 234 567 890"
                aria-label="Phone"
              />
            </div>
            <div className="flex flex-col gap-1">
              <Label htmlFor="contact-notes">Notes</Label>
              <Textarea
                id="contact-notes"
                className="h-24"
                value={editing.notes}
                onChange={(e) =>
                  setEditing({ ...editing, notes: e.target.value })
                }
                placeholder="Notes…"
                aria-label="Notes"
              />
            </div>
            <div className="flex gap-2 mt-2">
              <Button
                onClick={handleSave}
                disabled={!editing.name.trim()}
              >
                Save
              </Button>
              <Button
                variant="secondary"
                onClick={handleCancel}
              >
                Cancel
              </Button>
            </div>
          </div>
        ) : selected ? (
          <div className="p-6 flex flex-col gap-4">
            <div className="flex items-start justify-between">
              <div className="flex items-center gap-4">
                <div className="w-14 h-14 rounded-full bg-shell-surface flex items-center justify-center">
                  <User size={24} className="text-shell-text-secondary" />
                </div>
                <div>
                  <h2 className="text-xl font-semibold">{selected.name}</h2>
                </div>
              </div>
              <div className="flex gap-2">
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={handleEdit}
                  aria-label="Edit contact"
                >
                  Edit
                </Button>
                <Button
                  variant="ghost"
                  size="icon"
                  onClick={() => handleDelete(selected.id)}
                  className="h-8 w-8 hover:bg-red-500/15 hover:text-red-400"
                  aria-label="Delete contact"
                >
                  <Trash2 size={16} />
                </Button>
              </div>
            </div>

            <div className="flex flex-col gap-3 mt-2">
              {selected.email && (
                <div>
                  <div className="text-xs text-shell-text-tertiary mb-0.5">
                    Email
                  </div>
                  <div className="text-sm">{selected.email}</div>
                </div>
              )}
              {selected.phone && (
                <div>
                  <div className="text-xs text-shell-text-tertiary mb-0.5">
                    Phone
                  </div>
                  <div className="text-sm">{selected.phone}</div>
                </div>
              )}
              {selected.notes && (
                <div>
                  <div className="text-xs text-shell-text-tertiary mb-0.5">
                    Notes
                  </div>
                  <div className="text-sm whitespace-pre-wrap">
                    {selected.notes}
                  </div>
                </div>
              )}
            </div>
          </div>
        ) : (
          <div className="flex-1 flex items-center justify-center text-shell-text-tertiary text-sm">
            Select a contact or add a new one
          </div>
        )}
      </div>
    </div>
  );
}
