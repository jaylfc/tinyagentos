import { useState } from "react";
import { Plus, Search, Trash2, User } from "lucide-react";

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

  const inputClass =
    "w-full rounded-lg bg-shell-surface px-3 py-2 text-sm text-shell-text placeholder:text-shell-text-tertiary border border-white/5 focus:outline-none focus:ring-1 focus:ring-accent";

  return (
    <div className="flex h-full bg-shell-bg-deep text-shell-text select-none">
      {/* Sidebar */}
      <div className="w-56 shrink-0 flex flex-col border-r border-white/5">
        {/* Search + Add */}
        <div className="p-3 flex gap-2">
          <div className="relative flex-1">
            <Search
              size={14}
              className="absolute left-2.5 top-1/2 -translate-y-1/2 text-shell-text-tertiary"
            />
            <input
              type="text"
              placeholder="Search…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-full rounded-lg bg-shell-surface pl-8 pr-3 py-1.5 text-sm text-shell-text placeholder:text-shell-text-tertiary border border-white/5 focus:outline-none focus:ring-1 focus:ring-accent"
              aria-label="Search contacts"
            />
          </div>
          <button
            onClick={handleAdd}
            className="shrink-0 rounded-lg bg-accent/20 text-accent p-1.5 hover:bg-accent/30 transition-colors"
            aria-label="Add contact"
          >
            <Plus size={16} />
          </button>
        </div>

        {/* Contact list */}
        <div className="flex-1 overflow-y-auto">
          {filtered.length === 0 && (
            <p className="text-shell-text-tertiary text-xs text-center mt-8">
              {contacts.length === 0 ? "No contacts yet" : "No results"}
            </p>
          )}
          {filtered.map((c) => (
            <button
              key={c.id}
              onClick={() => {
                setSelectedId(c.id);
                setEditing(null);
              }}
              className={`w-full text-left px-3 py-2.5 flex items-center gap-2.5 transition-colors ${
                selectedId === c.id
                  ? "bg-accent/15 text-accent"
                  : "hover:bg-shell-surface"
              }`}
              aria-label={`Select ${c.name}`}
            >
              <div className="w-8 h-8 rounded-full bg-shell-surface flex items-center justify-center shrink-0">
                <User size={14} className="text-shell-text-secondary" />
              </div>
              <div className="min-w-0">
                <div className="text-sm font-medium truncate">{c.name}</div>
                {c.email && (
                  <div className="text-xs text-shell-text-secondary truncate">
                    {c.email}
                  </div>
                )}
              </div>
            </button>
          ))}
        </div>
      </div>

      {/* Detail panel */}
      <div className="flex-1 flex flex-col overflow-y-auto">
        {editing ? (
          <div className="p-6 flex flex-col gap-4 max-w-md">
            <h2 className="text-lg font-semibold">
              {contacts.find((c) => c.id === editing.id)
                ? "Edit Contact"
                : "New Contact"}
            </h2>
            <label className="flex flex-col gap-1">
              <span className="text-xs text-shell-text-secondary">Name</span>
              <input
                className={inputClass}
                value={editing.name}
                onChange={(e) =>
                  setEditing({ ...editing, name: e.target.value })
                }
                placeholder="Full name"
                aria-label="Name"
                autoFocus
              />
            </label>
            <label className="flex flex-col gap-1">
              <span className="text-xs text-shell-text-secondary">Email</span>
              <input
                className={inputClass}
                value={editing.email}
                onChange={(e) =>
                  setEditing({ ...editing, email: e.target.value })
                }
                placeholder="email@example.com"
                aria-label="Email"
              />
            </label>
            <label className="flex flex-col gap-1">
              <span className="text-xs text-shell-text-secondary">Phone</span>
              <input
                className={inputClass}
                value={editing.phone}
                onChange={(e) =>
                  setEditing({ ...editing, phone: e.target.value })
                }
                placeholder="+1 234 567 890"
                aria-label="Phone"
              />
            </label>
            <label className="flex flex-col gap-1">
              <span className="text-xs text-shell-text-secondary">Notes</span>
              <textarea
                className={inputClass + " resize-none h-24"}
                value={editing.notes}
                onChange={(e) =>
                  setEditing({ ...editing, notes: e.target.value })
                }
                placeholder="Notes…"
                aria-label="Notes"
              />
            </label>
            <div className="flex gap-2 mt-2">
              <button
                onClick={handleSave}
                disabled={!editing.name.trim()}
                className="px-4 py-2 rounded-lg bg-accent text-white text-sm font-medium hover:bg-accent/90 transition-colors disabled:opacity-40"
              >
                Save
              </button>
              <button
                onClick={handleCancel}
                className="px-4 py-2 rounded-lg bg-shell-surface text-shell-text-secondary text-sm hover:bg-shell-surface-hover transition-colors"
              >
                Cancel
              </button>
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
                <button
                  onClick={handleEdit}
                  className="px-3 py-1.5 rounded-lg bg-shell-surface text-sm text-shell-text-secondary hover:bg-shell-surface-hover transition-colors"
                  aria-label="Edit contact"
                >
                  Edit
                </button>
                <button
                  onClick={() => handleDelete(selected.id)}
                  className="p-1.5 rounded-lg bg-red-500/10 text-red-400 hover:bg-red-500/20 transition-colors"
                  aria-label="Delete contact"
                >
                  <Trash2 size={16} />
                </button>
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
