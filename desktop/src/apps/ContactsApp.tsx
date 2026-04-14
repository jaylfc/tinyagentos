import { useState } from "react";
import { Plus, Search, Trash2, User, X, Edit } from "lucide-react";
import { Button, Input, Textarea, Label, Card, CardContent } from "@/components/ui";
import { MobileSplitView } from "@/components/mobile/MobileSplitView";
import { useIsMobile } from "@/hooks/use-is-mobile";

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

/* ------------------------------------------------------------------ */
/*  Contact form — bottom sheet on mobile, modal on desktop            */
/* ------------------------------------------------------------------ */

function ContactForm({
  editing,
  isNew,
  onChange,
  onSave,
  onCancel,
}: {
  editing: Contact;
  isNew: boolean;
  onChange: (c: Contact) => void;
  onSave: () => void;
  onCancel: () => void;
}) {
  const isMobile = useIsMobile();

  return (
    <div
      className={
        isMobile
          ? "absolute inset-0 z-50 flex items-end bg-black/50 backdrop-blur-sm"
          : "absolute inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4"
      }
      onClick={onCancel}
      role="dialog"
      aria-modal="true"
      aria-label={isNew ? "Add contact" : "Edit contact"}
    >
      <Card
        className={
          isMobile
            ? "w-full max-h-[92%] overflow-y-auto bg-shell-surface shadow-2xl"
            : "w-full max-w-md max-h-full overflow-y-auto bg-shell-surface shadow-2xl"
        }
        style={isMobile ? { borderRadius: "20px 20px 0 0" } : undefined}
        onClick={(e) => e.stopPropagation()}
      >
        <CardContent className="p-5 space-y-4">
          {/* Header */}
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <User size={16} className="text-accent" />
              <h2 className="text-sm font-semibold">{isNew ? "New Contact" : "Edit Contact"}</h2>
            </div>
            <Button variant="ghost" size="icon" onClick={onCancel} aria-label="Close form" className="h-7 w-7">
              <X size={16} />
            </Button>
          </div>

          <div className="flex flex-col gap-1">
            <Label htmlFor="contact-name">Name</Label>
            <Input
              id="contact-name"
              value={editing.name}
              onChange={(e) => onChange({ ...editing, name: e.target.value })}
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
              onChange={(e) => onChange({ ...editing, email: e.target.value })}
              placeholder="email@example.com"
              aria-label="Email"
            />
          </div>
          <div className="flex flex-col gap-1">
            <Label htmlFor="contact-phone">Phone</Label>
            <Input
              id="contact-phone"
              value={editing.phone}
              onChange={(e) => onChange({ ...editing, phone: e.target.value })}
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
              onChange={(e) => onChange({ ...editing, notes: e.target.value })}
              placeholder="Notes…"
              aria-label="Notes"
            />
          </div>

          <div className="flex gap-2 pt-1">
            <Button onClick={onSave} disabled={!editing.name.trim()}>
              Save
            </Button>
            <Button variant="secondary" onClick={onCancel}>
              Cancel
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Contact detail pane                                                */
/* ------------------------------------------------------------------ */

function ContactDetail({
  contact,
  onEdit,
  onDelete,
}: {
  contact: Contact;
  onEdit: () => void;
  onDelete: () => void;
}) {
  const isMobile = useIsMobile();

  return (
    <div className="flex flex-col h-full min-h-0 overflow-hidden">
      {/* Header — desktop only; mobile nav bar from MobileSplitView shows the name */}
      {!isMobile && (
        <div className="flex items-start justify-between gap-3 px-4 py-3 border-b border-white/5 shrink-0">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-full bg-shell-surface flex items-center justify-center shrink-0">
              <User size={18} className="text-shell-text-secondary" />
            </div>
            <h2 className="text-sm font-semibold text-shell-text">{contact.name}</h2>
          </div>
          <div className="flex items-center gap-1 shrink-0">
            <Button size="sm" variant="outline" onClick={onEdit} aria-label={`Edit ${contact.name}`}>
              <Edit size={13} />
              Edit
            </Button>
            <Button
              size="sm"
              variant="outline"
              onClick={onDelete}
              className="hover:bg-red-500/15 hover:text-red-300"
              aria-label={`Delete ${contact.name}`}
            >
              <Trash2 size={13} />
              Delete
            </Button>
          </div>
        </div>
      )}

      {/* Mobile: avatar + action row */}
      {isMobile && (
        <div className="shrink-0 px-4 py-3 border-b border-white/5">
          <div className="flex items-center gap-3 mb-3">
            <div className="w-12 h-12 rounded-full bg-shell-surface flex items-center justify-center shrink-0">
              <User size={22} className="text-shell-text-secondary" />
            </div>
            <span className="text-base font-semibold text-shell-text">{contact.name}</span>
          </div>
          <div className="flex gap-2">
            <Button size="sm" variant="outline" onClick={onEdit} className="flex-1" aria-label={`Edit ${contact.name}`}>
              <Edit size={13} />
              Edit
            </Button>
            <Button
              size="sm"
              variant="outline"
              onClick={onDelete}
              className="flex-1 hover:bg-red-500/15 hover:text-red-300"
              aria-label={`Delete ${contact.name}`}
            >
              <Trash2 size={13} />
              Delete
            </Button>
          </div>
        </div>
      )}

      {/* Body */}
      <div className="flex-1 overflow-y-auto p-4 space-y-3">
        {contact.email && (
          <Card className="p-3">
            <CardContent className="p-0">
              <div className="text-[10px] uppercase tracking-wide text-shell-text-tertiary mb-1">Email</div>
              <div className="text-sm text-shell-text">{contact.email}</div>
            </CardContent>
          </Card>
        )}
        {contact.phone && (
          <Card className="p-3">
            <CardContent className="p-0">
              <div className="text-[10px] uppercase tracking-wide text-shell-text-tertiary mb-1">Phone</div>
              <div className="text-sm text-shell-text">{contact.phone}</div>
            </CardContent>
          </Card>
        )}
        {contact.notes && (
          <Card className="p-3">
            <CardContent className="p-0">
              <div className="text-[10px] uppercase tracking-wide text-shell-text-tertiary mb-1">Notes</div>
              <div className="text-sm text-shell-text whitespace-pre-wrap">{contact.notes}</div>
            </CardContent>
          </Card>
        )}
        {!contact.email && !contact.phone && !contact.notes && (
          <p className="text-xs text-shell-text-tertiary italic px-1">No details recorded</p>
        )}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  ContactsApp                                                        */
/* ------------------------------------------------------------------ */

export function ContactsApp({ windowId: _windowId }: { windowId: string }) {
  const isMobile = useIsMobile();
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
    setEditing(emptyContact());
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
  }

  function handleEdit() {
    if (selected) setEditing({ ...selected });
  }

  function handleCancel() {
    setEditing(null);
  }

  // Hide the app-level toolbar on mobile when detail is open —
  // MobileSplitView provides its own nav bar with back button there.
  const showToolbar = !isMobile || selectedId === null;

  return (
    <div className="flex flex-col h-full min-h-0 overflow-hidden bg-shell-bg-deep text-shell-text select-none relative">
      {/* Toolbar */}
      {showToolbar && (
        <div className="flex items-center justify-between px-4 py-3 border-b border-white/5 shrink-0">
          <div className="flex items-center gap-2 min-w-0">
            <User size={18} className="text-accent shrink-0" />
            <h1 className="text-sm font-semibold">Contacts</h1>
            <span className="text-xs text-shell-text-tertiary">{contacts.length} saved</span>
          </div>
          <Button size="sm" onClick={handleAdd} aria-label="Add contact">
            <Plus size={14} />
            {isMobile ? "Add" : "Add Contact"}
          </Button>
        </div>
      )}

      {/* Master-detail — MobileSplitView stacks on mobile, splits on desktop */}
      <MobileSplitView
        selectedId={selectedId}
        onBack={() => setSelectedId(null)}
        listTitle="Contacts"
        detailTitle={selected?.name}
        detailActions={
          isMobile && selected ? (
            <Button variant="ghost" size="sm" onClick={handleAdd} aria-label="Add contact" className="h-8">
              <Plus size={14} />
            </Button>
          ) : undefined
        }
        list={
          <div aria-label="Contact list">
            {/* Search bar */}
            <div className="p-3">
              <div className="relative">
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
            </div>

            {/* Empty states */}
            {filtered.length === 0 && (
              <p className="text-shell-text-tertiary text-xs text-center mt-8 px-4">
                {contacts.length === 0 ? "No contacts yet" : "No results"}
              </p>
            )}

            {/* iOS 26 grouped list on mobile */}
            {filtered.length > 0 && isMobile && (
              <div style={{ padding: "4px 0 16px" }}>
                <div
                  style={{
                    margin: "0 12px",
                    borderRadius: 16,
                    background: "rgba(255,255,255,0.05)",
                    border: "1px solid rgba(255,255,255,0.08)",
                    overflow: "hidden",
                  }}
                >
                  {filtered.map((c, idx, arr) => (
                    <button
                      key={c.id}
                      type="button"
                      onClick={() => setSelectedId(c.id)}
                      aria-label={`Select ${c.name}`}
                      style={{
                        display: "flex",
                        alignItems: "center",
                        gap: 10,
                        width: "100%",
                        padding: "14px 16px",
                        background: "none",
                        border: "none",
                        borderBottom: idx === arr.length - 1 ? "none" : "1px solid rgba(255,255,255,0.06)",
                        cursor: "pointer",
                        color: "inherit",
                        textAlign: "left",
                      }}
                    >
                      <div style={{ width: 32, height: 32, borderRadius: "50%", background: "rgba(255,255,255,0.08)", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
                        <User size={14} style={{ color: "rgba(255,255,255,0.5)" }} />
                      </div>
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <div style={{ fontSize: 15, fontWeight: 600, color: "rgba(255,255,255,0.95)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                          {c.name}
                        </div>
                        {c.email && (
                          <div style={{ fontSize: 12, color: "rgba(255,255,255,0.45)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                            {c.email}
                          </div>
                        )}
                      </div>
                      <svg width="8" height="14" viewBox="0 0 8 14" fill="none" style={{ color: "rgba(255,255,255,0.3)", flexShrink: 0 }}>
                        <path d="M1 1L7 7L1 13" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                      </svg>
                    </button>
                  ))}
                </div>
              </div>
            )}

            {/* Desktop list */}
            {filtered.length > 0 && !isMobile && (
              <div className="p-2 space-y-1">
                {filtered.map((c) => (
                  <Button
                    key={c.id}
                    variant={selectedId === c.id ? "secondary" : "ghost"}
                    onClick={() => setSelectedId(c.id)}
                    className="w-full justify-start h-auto py-2.5 px-3 rounded-lg font-normal"
                    aria-label={`Select ${c.name}`}
                  >
                    <div className="w-8 h-8 rounded-full bg-shell-surface flex items-center justify-center shrink-0">
                      <User size={14} className="text-shell-text-secondary" />
                    </div>
                    <div className="min-w-0 flex-1 text-left">
                      <div className="text-sm font-medium truncate">{c.name}</div>
                      {c.email && (
                        <div className="text-xs text-shell-text-secondary truncate">{c.email}</div>
                      )}
                    </div>
                  </Button>
                ))}
              </div>
            )}
          </div>
        }
        detail={
          selected ? (
            <ContactDetail
              contact={selected}
              onEdit={handleEdit}
              onDelete={() => handleDelete(selected.id)}
            />
          ) : !isMobile ? (
            <div className="flex-1 flex items-center justify-center h-full text-shell-text-tertiary text-sm">
              Select a contact or add a new one
            </div>
          ) : null
        }
      />

      {/* Contact form — bottom sheet on mobile, modal on desktop */}
      {editing && (
        <ContactForm
          editing={editing}
          isNew={!contacts.find((c) => c.id === editing.id)}
          onChange={setEditing}
          onSave={handleSave}
          onCancel={handleCancel}
        />
      )}
    </div>
  );
}
