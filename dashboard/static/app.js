const API = "";

function updateAiTabBadge() {
  const badge = document.getElementById("tab-ai-badge");
  if (!badge) return;
  const proposalsEl = document.getElementById("list-memory-agent");
  const proposals = proposalsEl ? proposalsEl.querySelectorAll("li").length : 0;
  if (proposals === 0) {
    badge.hidden = true;
    badge.textContent = "";
  } else {
    badge.hidden = false;
    badge.textContent = proposals > 9 ? "9+" : String(proposals);
  }
}

// Tab navigation
function initTabs() {
  const tabs = document.querySelectorAll(".tab");
  const contents = document.querySelectorAll(".tab-content");
  const stored = localStorage.getItem("woody-dashboard-tab");
  const defaultTab = stored || "overview";

  function showTab(tabId) {
    tabs.forEach((t) => t.classList.toggle("active", t.dataset.tab === tabId));
    contents.forEach((c) => c.classList.toggle("active", c.id === `tab-${tabId}`));
    localStorage.setItem("woody-dashboard-tab", tabId);
  }

  tabs.forEach((btn) => {
    btn.addEventListener("click", () => showTab(btn.dataset.tab));
  });
  showTab(defaultTab);
}
initTabs();

async function fetchJSON(path, opts = {}) {
  const res = await fetch(API + path, {
    ...opts,
    credentials: "include",
    headers: { "Content-Type": "application/json", ...opts.headers },
  });
  if (res.status === 401 && path !== "/api/auth/me") {
    window.location.href = "/login";
    throw new Error("Unauthorized");
  }
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

function showForm(type) {
  if (type === "note" || type === "todo") {
    ["note", "todo"].forEach((t) => {
      const f = document.getElementById(`form-${t}`);
      if (f) f.hidden = t !== type;
    });
  }
  const form = document.getElementById(`form-${type}`);
  if (!form) return;
  form.hidden = false;
  const today = new Date().toISOString().slice(0, 10);
  form.querySelectorAll('input[type="date"]').forEach((input) => {
    if (!input.value) input.value = today;
  });
}

function hideForm(type) {
  const form = document.getElementById(`form-${type}`);
  if (form) form.hidden = true;
}

// Events
document.querySelectorAll("[data-add]").forEach((btn) => {
  btn.addEventListener("click", () => showForm(btn.dataset.add));
});

document.querySelectorAll("[data-cancel]").forEach((btn) => {
  btn.addEventListener("click", () => hideForm(btn.dataset.cancel));
});

document.getElementById("form-event").addEventListener("submit", async (e) => {
  e.preventDefault();
  const fd = new FormData(e.target);
  await fetchJSON("/api/events", {
    method: "POST",
    body: JSON.stringify({
      date: fd.get("date"),
      title: fd.get("title"),
      description: fd.get("description") || "",
      event_type: fd.get("event_type") || "event",
      recurrence: fd.get("recurrence") || "",
    }),
  });
  e.target.reset();
  hideForm("event");
  loadEvents();
});

document.getElementById("form-decision").addEventListener("submit", async (e) => {
  e.preventDefault();
  const fd = new FormData(e.target);
  await fetchJSON("/api/decisions", {
    method: "POST",
    body: JSON.stringify({
      date: fd.get("date"),
      decision: fd.get("decision"),
      context: fd.get("context") || "",
      outcome: fd.get("outcome") || "",
    }),
  });
  e.target.reset();
  hideForm("decision");
  loadDecisions();
});

document.getElementById("form-note")?.addEventListener("submit", async (e) => {
  e.preventDefault();
  const fd = new FormData(e.target);
  await fetchJSON("/api/notes", {
    method: "POST",
    body: JSON.stringify({
      title: fd.get("title"),
      content: fd.get("content") || "",
      tags: fd.get("tags") || "",
    }),
  });
  e.target.reset();
  hideForm("note");
  loadNotesAndTodos();
});

document.getElementById("form-todo")?.addEventListener("submit", async (e) => {
  e.preventDefault();
  const fd = new FormData(e.target);
  const res = await fetchJSON("/api/todos", {
    method: "POST",
    body: JSON.stringify({
      content: fd.get("content"),
      due_date: (fd.get("due_date") || "").slice(0, 10) || "",
    }),
  });
  e.target.reset();
  hideForm("todo");
  if (res.ok) loadNotesAndTodos();
  else alert(res.error || "Failed to add todo.");
});

document.getElementById("btn-import-google")?.addEventListener("click", async () => {
  const btn = document.getElementById("btn-import-google");
  if (btn) btn.disabled = true;
  try {
    const res = await fetchJSON("/api/contacts/import/google", { method: "POST" });
    if (res.ok) {
      const parts = [`${res.added} added`, `${res.skipped} skipped`];
      if (res.circle_proposals) parts.push(`${res.circle_proposals} circle proposal(s)`);
      alert(`Imported: ${parts.join(", ")}.`);
      loadContacts();
      loadCircles();
      loadMemoryAgentProposals();
    } else {
      alert(res.message || "Import failed. Reconnect Google if needed.");
    }
  } catch (e) {
    alert("Error: " + (e.message || e));
  } finally {
    if (btn) btn.disabled = false;
  }
});

document.getElementById("vcard-file-input")?.addEventListener("change", async (e) => {
  const input = e.target;
  const file = input.files?.[0];
  if (!file) return;
  try {
    const fd = new FormData();
    fd.append("file", file);
    const res = await fetch(API + "/api/contacts/import/vcard", {
      method: "POST",
      body: fd,
    });
    const data = await res.json().catch(() => ({}));
    if (res.ok && data.ok) {
      alert(`Imported: ${data.added} added, ${data.skipped} skipped (existing).`);
      loadContacts();
    } else {
      alert(data.message || "Import failed.");
    }
  } catch (err) {
    alert("Error: " + (err.message || err));
  }
  input.value = "";
});

document.getElementById("form-contact")?.addEventListener("submit", async (e) => {
  e.preventDefault();
  const fd = new FormData(e.target);
  await fetchJSON("/api/contacts", {
    method: "POST",
    body: JSON.stringify({
      name: fd.get("name"),
      email: fd.get("email") || "",
      phone: fd.get("phone") || "",
      notes: fd.get("notes") || "",
    }),
  });
  e.target.reset();
  hideForm("contact");
  loadContacts();
});

document.getElementById("form-place")?.addEventListener("submit", async (e) => {
  e.preventDefault();
  const fd = new FormData(e.target);
  await fetchJSON("/api/places", {
    method: "POST",
    body: JSON.stringify({
      name: fd.get("name"),
      address: fd.get("address") || "",
      notes: fd.get("notes") || "",
    }),
  });
  e.target.reset();
  hideForm("place");
  loadPlaces();
});

document.getElementById("form-circle")?.addEventListener("submit", async (e) => {
  e.preventDefault();
  const fd = new FormData(e.target);
  await fetchJSON("/api/circles", {
    method: "POST",
    body: JSON.stringify({
      name: fd.get("name"),
      description: fd.get("description") || "",
    }),
  });
  e.target.reset();
  hideForm("circle");
  loadCircles();
});

document.getElementById("form-scheduled-template")?.addEventListener("submit", async (e) => {
  e.preventDefault();
  const fd = new FormData(e.target);
  await fetchJSON("/api/scheduled-templates", {
    method: "POST",
    body: JSON.stringify({
      title: fd.get("title"),
      description: fd.get("description") || "",
      recurrence: fd.get("recurrence"),
      anchor_date: fd.get("anchor_date"),
    }),
  });
  e.target.reset();
  hideForm("scheduled-template");
  loadScheduledTemplates();
  loadEvents();
});

document.getElementById("form-wishlist")?.addEventListener("submit", async (e) => {
  e.preventDefault();
  const fd = new FormData(e.target);
  try {
    await fetchJSON("/api/wishlist", {
      method: "POST",
      body: JSON.stringify({ content: fd.get("content") }),
    });
    e.target.reset();
    hideForm("wishlist");
    loadWishlist();
  } catch (err) {
    alert("Failed to add: " + (err.message || err));
  }
});

document.getElementById("form-memory")?.addEventListener("submit", async (e) => {
  e.preventDefault();
  const fd = new FormData(e.target);
  const fact = fd.get("fact")?.toString()?.trim();
  if (!fact) return;
  try {
    const res = await fetchJSON("/api/memories", {
      method: "POST",
      body: JSON.stringify({ fact }),
    });
    e.target.reset();
    hideForm("memory");
    loadMemories();
    if (!res.ok) alert(res.message || "Failed to save memory.");
  } catch (err) {
    alert("Failed to save memory: " + (err.message || err));
  }
});

function formatDate(s) {
  if (!s) return "";
  const d = new Date(s + "T12:00:00");
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
}

function renderEvent(e) {
  const deleteBtn = e.id != null && e.source !== "google"
    ? `<button class="btn btn-danger" data-delete-event="${e.id}">Delete</button>`
    : "";
  const addToCalBtn = e.id != null && e.source !== "google"
    ? `<button class="btn btn-primary" data-create-calendar="${e.id}">Add to Calendar</button>`
    : "";
  const addToTodoBtn = `<button class="btn btn-add" data-add-todo title="Add to TODO list" data-add-todo-title="${escapeAttr(e.title || "")}" data-add-todo-date="${escapeAttr((e.date || "").slice(0, 10))}" data-add-todo-event-id="${e.id != null ? e.id : ""}">Add to TODO</button>`;
  return `
    <li>
      <div class="item-header">
        <span class="item-title">${escapeHtml(e.title)}</span>
        <span class="item-date">${formatDate(e.date)}</span>
      </div>
      ${e.description ? `<p class="item-desc event-desc">${escapeHtml(htmlToPlainText(e.description))}</p>` : ""}
      <div class="item-header">
        <span class="badge">${escapeHtml(e.event_type || "event")}</span>
        ${addToCalBtn}
        ${addToTodoBtn}
        ${deleteBtn}
      </div>
    </li>
  `;
}

function renderDecision(d) {
  return `
    <li>
      <div class="item-header">
        <span class="item-title">${escapeHtml(d.decision)}</span>
        <span class="item-date">${formatDate(d.date)}</span>
      </div>
      ${d.context ? `<p class="item-desc">${escapeHtml(d.context)}</p>` : ""}
      ${d.outcome ? `<p class="item-meta">Outcome: ${escapeHtml(d.outcome)}</p>` : ""}
      <div class="item-actions">
        <button class="btn btn-danger" data-delete-decision="${d.id}">Delete</button>
      </div>
    </li>
  `;
}

function renderNoteItem(n) {
  return `
    <li class="notes-todos-item notes-todos-note" data-type="note" data-id="${n.id}">
      <span class="item-type-badge badge-note" title="Note – reference info">Note</span>
      <div class="item-header">
        <span class="item-title">${escapeHtml(n.title)}</span>
      </div>
      ${n.content ? `<p class="item-desc">${escapeHtml(n.content)}</p>` : ""}
      ${n.tags ? `<p class="item-meta">${escapeHtml(n.tags)}</p>` : ""}
      <p class="item-meta">${formatDate(n.updated_at?.slice(0, 10) || n.created_at?.slice(0, 10))}</p>
      <div class="item-actions">
        <button class="btn btn-danger" data-delete-note="${n.id}">Delete</button>
      </div>
    </li>
  `;
}

function renderTodoItem(t) {
  const done = t.status === "done";
  const dueStr = t.due_date ? ` <span class="item-due">due ${formatDate(t.due_date)}</span>` : "";
  return `
    <li class="notes-todos-item notes-todos-todo ${done ? "notes-todos-done" : ""}" data-type="todo" data-id="${t.id}">
      <span class="item-type-badge badge-todo" title="Todo – task to complete">${done ? "✓" : "○"}</span>
      <div class="item-header">
        <span class="item-title ${done ? "item-title-done" : ""}">${escapeHtml(t.content || "")}</span>${dueStr}
      </div>
      <p class="item-meta">${formatDate(t.created_at?.slice(0, 10))}</p>
      <div class="item-actions">
        ${!done ? `<button class="btn btn-primary" data-complete-todo="${t.id}">Done</button>` : ""}
        <button class="btn btn-danger" data-delete-todo="${t.id}">Delete</button>
      </div>
    </li>
  `;
}

function renderWishlistItem(w) {
  return `
    <li>
      <p class="item-desc">${escapeHtml(w.content || "")}</p>
      <div class="item-actions">
        <button class="btn btn-primary" data-fulfill-wishlist="${w.id}" title="Mark as fulfilled (creates event)">Fulfill</button>
        <button class="btn btn-danger" data-delete-wishlist="${w.id}">Remove</button>
      </div>
    </li>
  `;
}

function escapeHtml(s) {
  if (s == null) return "";
  const div = document.createElement("div");
  div.textContent = String(s);
  return div.innerHTML;
}

/** Convert HTML (e.g. from Google Calendar) to readable plain text with line breaks. */
function htmlToPlainText(html) {
  if (html == null || !String(html).trim()) return "";
  let s = String(html)
    .replace(/<br\s*\/?>/gi, "\n")
    .replace(/<\/p>/gi, "\n")
    .replace(/<p[^>]*>/gi, "\n")
    .replace(/<[^>]+>/g, "")
    .replace(/&amp;/g, "&")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&nbsp;/g, " ")
    .replace(/&#39;/g, "'")
    .replace(/&quot;/g, '"')
    .trim()
    .replace(/\n{3,}/g, "\n\n");
  return s;
}

function escapeAttr(s) {
  if (s == null) return "";
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/"/g, "&quot;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

function normalizeEventKey(ev) {
  const d = (ev.date || "").slice(0, 10);
  const t = (ev.title || "").toLowerCase().replace(/\s+/g, " ").trim().slice(0, 80);
  return d && t ? `${d}|${t}` : null;
}

async function loadEvents() {
  const [dashboardEvents, calendarEvents] = await Promise.all([
    fetchJSON("/api/events?coming=1"),
    fetchJSON("/api/events/calendar").catch(() => []),
  ]);
  const seen = new Set();
  const events = [];
  for (const ev of [...dashboardEvents, ...calendarEvents]) {
    const key = normalizeEventKey(ev);
    if (key && seen.has(key)) continue;
    if (key) seen.add(key);
    events.push(ev);
  }
  events.sort((a, b) => (a.date || "").localeCompare(b.date || ""));
  const list = document.getElementById("list-events");
  list.innerHTML = events.length
    ? events.map(renderEvent).join("")
    : '<li class="empty">No coming events. Add one above or connect Google Calendar.</li>';
  list.querySelectorAll("[data-delete-event]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      await fetchJSON(`/api/events/${btn.dataset.deleteEvent}`, { method: "DELETE" });
      loadEvents();
    });
  });
  const reqSection = document.getElementById("requires-scheduling");
  const reqList = document.getElementById("list-requires-scheduling");
  if (reqSection && reqList) {
    try {
      const reqItems = await fetchJSON("/api/events/requires-scheduling?days=14");
      if (reqItems.length) {
        reqSection.hidden = false;
        reqList.innerHTML = reqItems.map((r) => `
          <li>
            <p class="item-desc">${escapeHtml(r.title || "")} <span class="badge">due ${r.next_due}</span></p>
            <div class="item-actions">
              <button class="btn btn-primary" data-schedule-now="${r.id}">Schedule now</button>
            </div>
          </li>
        `).join("");
        reqList.querySelectorAll("[data-schedule-now]").forEach((btn) => {
          btn.addEventListener("click", async () => {
            const id = btn.dataset.scheduleNow;
            if (!id) return;
            btn.disabled = true;
            try {
              const res = await fetchJSON(`/api/scheduled-templates/${id}/schedule-now`, { method: "POST" });
              if (res.ok) {
                loadEvents();
                loadScheduledTemplates();
              } else {
                alert(res.error || "Failed.");
              }
            } catch (e) {
              alert("Error: " + (e.message || e));
            } finally {
              btn.disabled = false;
            }
          });
        });
      } else {
        reqSection.hidden = true;
      }
    } catch {
      reqSection.hidden = true;
    }
  }
  list.querySelectorAll("[data-create-calendar]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const id = btn.dataset.createCalendar;
      try {
        const res = await fetchJSON(`/api/events/${id}/create-in-calendar`, { method: "POST" });
        if (res.ok) {
          btn.textContent = "Added ✓";
          btn.disabled = true;
        } else {
          alert(res.message || "Failed to add to Calendar.");
        }
      } catch (err) {
        alert("Failed: " + (err.message || err));
      }
    });
  });
  list.querySelectorAll("[data-add-todo]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const title = btn.dataset.addTodoTitle || "";
      const date = btn.dataset.addTodoDate || "";
      const eventId = btn.dataset.addTodoEventId ? parseInt(btn.dataset.addTodoEventId, 10) : null;
      if (!title.trim()) return;
      btn.disabled = true;
      try {
        const body = { content: title.trim(), due_date: date };
        if (eventId && !isNaN(eventId)) body.event_id = eventId;
        const res = await fetchJSON("/api/todos", {
          method: "POST",
          body: JSON.stringify(body),
        });
        if (res.ok) {
          btn.textContent = "Added ✓";
          loadNotesAndTodos();
        } else {
          btn.disabled = false;
          alert(res.error || "Failed to add to TODO.");
        }
      } catch (err) {
        btn.disabled = false;
        alert("Failed: " + (err.message || err));
      }
    });
  });
  // Load and show duplicates
  const dupSection = document.getElementById("event-duplicates");
  const dupList = document.getElementById("list-duplicates");
  if (dupSection && dupList) {
    try {
      const dupData = await fetchJSON("/api/events/duplicates");
      const dups = dupData.duplicates || [];
      if (dups.length) {
        dupSection.hidden = false;
        dupList.innerHTML = dups.map((group) => {
          const keep = group[0];
          const others = group.slice(1);
          const ids = group.map((e) => e.id);
          return `
            <li class="duplicate-group">
              <p class="item-desc">${escapeHtml(keep.date || "")}: ${escapeHtml(keep.title || "")} <span class="badge">${group.length} copies</span></p>
              <div class="item-actions">
                <button class="btn btn-primary btn-merge-duplicates" data-keep-id="${keep.id}" data-delete-ids="${others.map((e) => e.id).join(",")}">Keep first, remove ${others.length} other(s)</button>
              </div>
            </li>
          `;
        }).join("");
        dupList.querySelectorAll(".btn-merge-duplicates").forEach((btn) => {
          btn.addEventListener("click", async () => {
            const keepId = btn.dataset.keepId;
            const deleteIds = (btn.dataset.deleteIds || "").split(",").filter(Boolean);
            if (!keepId || !deleteIds.length) return;
            btn.disabled = true;
            try {
              const res = await fetchJSON("/api/events/merge", {
                method: "POST",
                body: JSON.stringify({ keep_id: parseInt(keepId, 10), delete_ids: deleteIds.map((x) => parseInt(x, 10)) }),
              });
              if (res.ok) {
                loadEvents();
              } else {
                alert(res.message || "Merge failed.");
                btn.disabled = false;
              }
            } catch (e) {
              alert("Merge failed: " + (e.message || e));
              btn.disabled = false;
            }
          });
        });
      } else {
        dupSection.hidden = true;
        dupList.innerHTML = "";
      }
    } catch {
      dupSection.hidden = true;
    }
  }
}

async function loadDecisions() {
  const decisions = await fetchJSON("/api/decisions");
  const list = document.getElementById("list-decisions");
  list.innerHTML = decisions.length
    ? decisions.map(renderDecision).join("")
    : '<li class="empty">No decisions yet. Add one above.</li>';
  list.querySelectorAll("[data-delete-decision]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      await fetchJSON(`/api/decisions/${btn.dataset.deleteDecision}`, { method: "DELETE" });
      loadDecisions();
    });
  });
}

async function loadNotesAndTodos() {
  const [notes, todos] = await Promise.all([
    fetchJSON("/api/notes"),
    fetchJSON("/api/todos").catch(() => []),
  ]);
  const noteItems = notes.map((n) => ({ ...n, _order: 1, _sort: n.updated_at || n.created_at || "", _type: "note" }));
  const todoItems = todos.map((t) => ({
    ...t,
    _order: t.status === "done" ? 2 : 0,
    _sort: t.due_date || "9999-99-99",
    _type: "todo",
  }));
  const combined = [...noteItems, ...todoItems].sort((a, b) => {
    if (a._order !== b._order) return a._order - b._order;
    if (a._order === 0) return (a._sort || "").localeCompare(b._sort || "");
    if (a._order === 1) return (b._sort || "").localeCompare(a._sort || "");
    return (b._sort || "").localeCompare(a._sort || "");
  });
  const list = document.getElementById("list-notes-todos");
  if (!list) return;
  list.innerHTML = combined.length
    ? combined.map((item) => (item._type === "note" ? renderNoteItem(item) : renderTodoItem(item))).join("")
    : '<li class="empty">No notes or todos yet. Add a note or todo above.</li>';
  list.querySelectorAll("[data-delete-note]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      await fetchJSON(`/api/notes/${btn.dataset.deleteNote}`, { method: "DELETE" });
      loadNotesAndTodos();
    });
  });
  list.querySelectorAll("[data-delete-todo]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const res = await fetchJSON(`/api/todos/${btn.dataset.deleteTodo}`, { method: "DELETE" });
      if (res.ok) loadNotesAndTodos();
      else alert(res.error || "Failed to delete.");
    });
  });
  list.querySelectorAll("[data-complete-todo]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const res = await fetchJSON(`/api/todos/${btn.dataset.completeTodo}/complete`, { method: "PATCH" });
      if (res.ok) loadNotesAndTodos();
      else alert(res.error || "Failed to complete.");
    });
  });
}

function formatOtelTime(ms) {
  if (ms == null) return "-";
  if (ms < 1000) return ms.toFixed(1) + "ms";
  return (ms / 1000).toFixed(2) + "s";
}

function renderOtelSpan(s) {
  const statusClass = s.status === "ERROR" ? "status-error" : s.status === "OK" ? "status-ok" : "";
  const time = s.start_time ? new Date(s.start_time / 1_000_000).toLocaleTimeString() : "-";
  return `
    <li class="otel-span ${statusClass}">
      <div class="item-header">
        <span class="item-title otel-name">${escapeHtml(s.name)}</span>
        <span class="item-date">${time}</span>
      </div>
      <div class="otel-meta">
        ${s.duration_ms != null ? `<span>${formatOtelTime(s.duration_ms)}</span>` : ""}
        ${s.status ? `<span class="badge">${escapeHtml(s.status)}</span>` : ""}
      </div>
      ${(s.attributes && Object.keys(s.attributes).length) ? `<pre class="otel-attrs">${escapeHtml(JSON.stringify(s.attributes).slice(0, 120))}${JSON.stringify(s.attributes).length > 120 ? "…" : ""}</pre>` : ""}
    </li>
  `;
}

async function loadOtelTraces() {
  try {
    const data = await fetchJSON("/api/otel/traces?limit=30");
    const list = document.getElementById("list-otel");
    list.innerHTML = data.spans?.length
      ? data.spans.map(renderOtelSpan).join("")
      : '<li class="empty">No traces yet. Use the dashboard to generate activity.</li>';
  } catch (e) {
    document.getElementById("list-otel").innerHTML =
      '<li class="empty">Unable to load traces.</li>';
  }
}

document.getElementById("btn-refresh-otel")?.addEventListener("click", loadOtelTraces);

function renderContact(c, isEditing = false) {
  const editingClass = isEditing ? " contact-item-editing" : "";
  return `
    <li class="contact-item${editingClass}" data-contact-id="${c.id}">
      <div class="contact-view">
        <div class="item-header">
          <span class="item-title">${escapeHtml(c.name || "")}</span>
        </div>
        ${c.email ? `<p class="item-meta">${escapeHtml(c.email)}</p>` : ""}
        ${c.phone ? `<p class="item-meta">${escapeHtml(c.phone)}</p>` : ""}
        ${c.notes ? `<p class="item-desc">${escapeHtml(c.notes)}</p>` : ""}
        <div class="item-actions">
          <button class="btn btn-add" data-edit-contact="${c.id}">Edit</button>
          <button class="btn btn-danger" data-delete-contact="${c.id}">Delete</button>
        </div>
      </div>
      <div class="contact-edit-form">
        <input type="text" class="contact-edit-name" value="${escapeAttr(c.name || "")}" placeholder="Name" required>
        <input type="email" class="contact-edit-email" value="${escapeAttr(c.email || "")}" placeholder="Email">
        <input type="text" class="contact-edit-phone" value="${escapeAttr(c.phone || "")}" placeholder="Phone">
        <textarea class="contact-edit-notes" rows="2" placeholder="Notes">${escapeHtml(c.notes || "")}</textarea>
        <div class="form-actions">
          <button type="button" class="btn btn-primary btn-contact-save" data-contact-id="${c.id}">Save</button>
          <button type="button" class="btn btn-cancel btn-contact-cancel" data-contact-id="${c.id}">Cancel</button>
        </div>
      </div>
    </li>
  `;
}

function renderPlace(p) {
  return `
    <li>
      <div class="item-header">
        <span class="item-title">${escapeHtml(p.name)}</span>
      </div>
      ${p.address ? `<p class="item-meta">${escapeHtml(p.address)}</p>` : ""}
      ${p.notes ? `<p class="item-desc">${escapeHtml(p.notes)}</p>` : ""}
      <div class="item-actions">
        <button class="btn btn-danger" data-delete-place="${p.id}">Delete</button>
      </div>
    </li>
  `;
}

function renderCircle(c) {
  const memberCount = c.members?.length || 0;
  return `
    <li>
      <div class="item-header">
        <span class="item-title">${escapeHtml(c.name)}</span>
      </div>
      ${c.description ? `<p class="item-desc">${escapeHtml(c.description)}</p>` : ""}
      <p class="item-meta">${memberCount} member${memberCount !== 1 ? "s" : ""}</p>
      <div class="item-actions">
        <button class="btn btn-danger" data-delete-circle="${c.id}">Delete</button>
      </div>
    </li>
  `;
}

function renderMemory(m) {
  const text = m.text || m.fact || "";
  const id = m.id;
  const deleteBtn = id
    ? `<button class="btn btn-danger" data-delete-memory="${escapeHtml(id)}">Remove</button>`
    : "";
  return `
    <li>
      <p class="item-desc">${escapeHtml(text)}</p>
      ${deleteBtn ? `<div class="item-actions">${deleteBtn}</div>` : ""}
    </li>
  `;
}

let contactsCache = [];

function filterContacts(contacts, query) {
  if (!query || !query.trim()) return contacts;
  const q = query.trim().toLowerCase();
  return contacts.filter(
    (c) =>
      (c.name || "").toLowerCase().includes(q) ||
      (c.email || "").toLowerCase().includes(q) ||
      (c.phone || "").toLowerCase().includes(q) ||
      (c.notes || "").toLowerCase().includes(q)
  );
}

function renderContactsList(contacts, listEl) {
  if (!listEl) return;
  const emptyMsg =
    contactsCache.length === 0
      ? "No contacts yet. Add one above."
      : "No contacts match.";
  listEl.innerHTML = contacts.length
    ? contacts.map((c) => renderContact(c)).join("")
    : `<li class="empty">${emptyMsg}</li>`;
  bindContactActions(listEl);
}

function bindContactActions(listEl) {
  if (!listEl) return;
  listEl.querySelectorAll("[data-delete-contact]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      await fetchJSON(`/api/contacts/${btn.dataset.deleteContact}`, { method: "DELETE" });
      loadContacts();
    });
  });
  listEl.querySelectorAll("[data-edit-contact]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const id = parseInt(btn.dataset.editContact, 10);
      const item = listEl.querySelector(`.contact-item[data-contact-id="${id}"]`);
      if (item) item.classList.add("contact-item-editing");
    });
  });
  listEl.querySelectorAll(".btn-contact-save").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const id = parseInt(btn.dataset.contactId, 10);
      const item = listEl.querySelector(`.contact-item[data-contact-id="${id}"]`);
      if (!item) return;
      const name = item.querySelector(".contact-edit-name")?.value?.trim();
      if (!name) return;
      const email = item.querySelector(".contact-edit-email")?.value?.trim() || "";
      const phone = item.querySelector(".contact-edit-phone")?.value?.trim() || "";
      const notes = item.querySelector(".contact-edit-notes")?.value?.trim() || "";
      try {
        await fetchJSON(`/api/contacts/${id}`, {
          method: "PATCH",
          body: JSON.stringify({ name, email, phone, notes }),
        });
        const c = contactsCache.find((x) => x.id === id);
        if (c) {
          c.name = name;
          c.email = email;
          c.phone = phone;
          c.notes = notes;
        }
        item.classList.remove("contact-item-editing");
        renderContactsList(filterContacts(contactsCache, document.getElementById("contacts-search")?.value || ""), listEl);
      } catch (e) {
        alert("Failed to save: " + (e.message || e));
      }
    });
  });
  listEl.querySelectorAll(".btn-contact-cancel").forEach((btn) => {
    btn.addEventListener("click", () => {
      const id = parseInt(btn.dataset.contactId, 10);
      const item = listEl.querySelector(`.contact-item[data-contact-id="${id}"]`);
      if (item) item.classList.remove("contact-item-editing");
    });
  });
}

async function loadContacts() {
  try {
    contactsCache = await fetchJSON("/api/contacts");
    const list = document.getElementById("list-contacts");
    const body = document.getElementById("contacts-list-body");
    const countEl = document.getElementById("contacts-count");
    const searchInput = document.getElementById("contacts-search");
    if (!list) return;

    const query = searchInput?.value?.trim() || "";
    const filtered = filterContacts(contactsCache, query);
    const icon = document.getElementById("contacts-collapse-icon");
    if (countEl) {
      const n = contactsCache.length;
      countEl.textContent =
        n === 0
          ? "No contacts"
          : filtered.length === n
            ? `${n} contact${n !== 1 ? "s" : ""}`
            : `${filtered.length} of ${n} contacts`;
    }
    renderContactsList(filtered, list);

    if (body) {
      if (contactsCache.length === 0) {
        body.classList.remove("collapsed");
        if (icon) icon.textContent = "▼";
      } else if (icon) {
        icon.textContent = body.classList.contains("collapsed") ? "▶" : "▼";
      }
    }
  } catch (e) {
    const list = document.getElementById("list-contacts");
    if (list) list.innerHTML = '<li class="empty">Unable to load contacts.</li>';
  }
}

function initContactsSearchAndCollapse() {
  const searchInput = document.getElementById("contacts-search");
  const collapseBtn = document.getElementById("btn-contacts-collapse");
  const body = document.getElementById("contacts-list-body");
  const icon = document.getElementById("contacts-collapse-icon");

  let searchDebounce;
  searchInput?.addEventListener("input", function () {
    clearTimeout(searchDebounce);
    searchDebounce = setTimeout(() => {
      const filtered = filterContacts(contactsCache, this.value);
      const list = document.getElementById("list-contacts");
      renderContactsList(filtered, list);
      const countEl = document.getElementById("contacts-count");
      if (countEl) {
        const n = contactsCache.length;
        countEl.textContent =
          n === 0
            ? "No contacts"
            : filtered.length === n
              ? `${n} contact${n !== 1 ? "s" : ""}`
              : `${filtered.length} of ${n} contacts`;
      }
    }, 200);
  });

  collapseBtn?.addEventListener("click", () => {
    body?.classList.toggle("collapsed");
    if (icon) icon.textContent = body?.classList.contains("collapsed") ? "▶" : "▼";
  });
}

async function loadPlaces() {
  try {
    const places = await fetchJSON("/api/places");
    const list = document.getElementById("list-places");
    if (!list) return;
    list.innerHTML = places.length
      ? places.map(renderPlace).join("")
      : '<li class="empty">No places yet. Add one above.</li>';
    list.querySelectorAll("[data-delete-place]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        await fetchJSON(`/api/places/${btn.dataset.deletePlace}`, { method: "DELETE" });
        loadPlaces();
      });
    });
  } catch (e) {
    const list = document.getElementById("list-places");
    if (list) list.innerHTML = '<li class="empty">Unable to load places.</li>';
  }
}

async function loadCircles() {
  try {
    const circles = await fetchJSON("/api/circles");
    const list = document.getElementById("list-circles");
    if (!list) return;
    const withMembers = await Promise.all(
      circles.map((c) => fetchJSON(`/api/circles/${c.id}`).catch(() => ({ ...c, members: [] })))
    );
    list.innerHTML = withMembers.length
      ? withMembers.map(renderCircle).join("")
      : '<li class="empty">No circles yet. Create one to connect people, places & memories.</li>';
    list.querySelectorAll("[data-delete-circle]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        await fetchJSON(`/api/circles/${btn.dataset.deleteCircle}`, { method: "DELETE" });
        loadCircles();
      });
    });
  } catch (e) {
    const list = document.getElementById("list-circles");
    if (list) list.innerHTML = '<li class="empty">Unable to load circles.</li>';
  }
}

async function loadMemories(query) {
  try {
    const url = query ? `/api/memories?q=${encodeURIComponent(query)}` : "/api/memories";
    const data = await fetchJSON(url);
    const list = document.getElementById("list-memories");
    if (!list) return;
    const mems = data.memories || [];
    const emptyMsg = query
      ? "No memories match your search."
      : "No memories yet. Add one above or ask Woody to remember something.";
    list.innerHTML = mems.length
      ? mems.map(renderMemory).join("")
      : `<li class="empty">${emptyMsg}</li>`;
    if (data.error) {
      list.innerHTML = `<li class="empty">${escapeHtml(data.error)} (install chromadb)</li>`;
    }
    list.querySelectorAll("[data-delete-memory]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const id = btn.dataset.deleteMemory;
        if (!id) return;
        const res = await fetchJSON(`/api/memories/${encodeURIComponent(id)}`, { method: "DELETE" });
        if (res.ok) loadMemories(query);
        else alert(res.message || "Failed to delete memory.");
      });
    });
  } catch (e) {
    const list = document.getElementById("list-memories");
    if (list) list.innerHTML = '<li class="empty">Unable to load memories.</li>';
  }
}

let memorySearchDebounce;
document.getElementById("memory-search")?.addEventListener("input", function () {
  clearTimeout(memorySearchDebounce);
  const q = this.value.trim();
  memorySearchDebounce = setTimeout(() => loadMemories(q), 300);
});

function renderProposalDetails(type, payload) {
  if (type === "consolidate") {
    const texts = payload.source_texts || [];
    const merged = payload.merged_text || "";
    return `
      <div class="proposal-detail-section">
        <p class="proposal-detail-label">Memory 1:</p>
        <p class="proposal-detail-text">${escapeHtml(texts[0] || "(no text)")}</p>
        <p class="proposal-detail-label">Memory 2:</p>
        <p class="proposal-detail-text">${escapeHtml(texts[1] || "(no text)")}</p>
        <p class="proposal-detail-label">Merged result:</p>
        <p class="proposal-detail-text">${escapeHtml(merged)}</p>
      </div>
    `;
  }
  if (type === "add") return `<p class="proposal-detail-text">${escapeHtml(payload.fact || "")}</p>`;
  if (type === "remove") return `<p class="proposal-detail-text">Query: ${escapeHtml(payload.query || "")}</p>`;
  if (type === "event_memory") return `<p class="proposal-detail-text">${escapeHtml(payload.text || "")}</p>`;
  if (type === "event_suggestion") {
    return `
      <div class="proposal-detail-section">
        <p class="proposal-detail-label">Title:</p>
        <p class="proposal-detail-text">${escapeHtml(payload.title || "")}</p>
        ${payload.description ? `<p class="proposal-detail-label">From email:</p><p class="proposal-detail-text">${escapeHtml(htmlToPlainText(payload.description))}</p>` : ""}
      </div>
    `;
  }
  if (type === "circle_add") return `<p class="proposal-detail-text">Add ${payload.entity_id} to ${payload.circle_name || "circle"}. Reason: ${escapeHtml(payload.reason_activity || "")}</p>`;
  if (type === "promote") return `<p class="proposal-detail-text">${escapeHtml(payload.text || "")}</p>`;
  return `<pre class="proposal-detail-json">${escapeHtml(JSON.stringify(payload, null, 2))}</pre>`;
}

function renderMemoryAgentProposal(p) {
  const type = p.action_type || "unknown";
  const payload = p.payload || {};
  let desc = "";
  if (type === "add") desc = `Add: ${(payload.fact || "").slice(0, 80)}…`;
  else if (type === "remove") desc = `Remove by query: ${(payload.query || "").slice(0, 60)}`;
  else if (type === "event_memory") desc = `Event: ${(payload.text || "").slice(0, 80)}…`;
  else if (type === "event_suggestion") {
    desc = `Create event: ${(payload.title || "").slice(0, 60)}… (from email)`;
    if (payload.suggested_action === "calendar") desc += " [User often adds similar to Calendar]";
    else if (payload.suggested_action === "todo") desc += " [User often adds similar to TODO]";
  }
  else if (type === "circle_add") desc = `Add contact ${payload.entity_id || "?"} to ${payload.circle_name || "circle"} (${payload.reason_activity || ""})`;
  else if (type === "consolidate") desc = `Merge ${(payload.source_ids || []).length} memories`;
  else if (type === "promote") desc = `${payload.action || ""}: ${(payload.text || "").slice(0, 60)}…`;
  else desc = JSON.stringify(payload).slice(0, 80);
  const reason = p.reason ? ` (${escapeHtml(p.reason)})` : "";
  const eventSuggestionBtns = type === "event_suggestion"
    ? `<button class="btn btn-add btn-proposal-add-todo" data-title="${escapeAttr(payload.title || "")}" data-date="${escapeAttr((payload.date || "").slice(0, 10))}" title="Add to TODO without approving">Add to TODO</button>`
    : "";
  const detailsHtml = renderProposalDetails(type, payload);
  return `
    <li class="memory-agent-item" data-proposal-id="${escapeHtml(p.id)}">
      <p class="item-desc"><span class="badge">${escapeHtml(type)}</span> ${escapeHtml(desc)}${reason}</p>
      <div class="proposal-details" hidden>${detailsHtml}</div>
      <div class="item-actions">
        <button class="btn btn-add btn-proposal-expand" type="button" title="Show full details">▼ Details</button>
        ${eventSuggestionBtns}
        <button class="btn btn-primary btn-mem-agent-approve" data-id="${escapeHtml(p.id)}">Approve</button>
        <button class="btn btn-danger btn-mem-agent-reject" data-id="${escapeHtml(p.id)}">Reject</button>
      </div>
    </li>
  `;
}

async function loadMemoryAgentProposals() {
  try {
    const data = await fetchJSON("/api/memory-agent/proposals");
    const container = document.getElementById("memory-agent-proposals");
    const list = document.getElementById("list-memory-agent");
    if (!container || !list) return;
    const proposals = data.proposals || [];
    if (proposals.length === 0) {
      container.hidden = true;
      list.innerHTML = "";
      updateAiTabBadge();
      return;
    }
    container.hidden = false;
    updateAiTabBadge();
    list.innerHTML = proposals.map(renderMemoryAgentProposal).join("");
    list.querySelectorAll(".btn-proposal-expand").forEach((btn) => {
      btn.addEventListener("click", () => {
        const item = btn.closest(".memory-agent-item");
        const details = item?.querySelector(".proposal-details");
        if (!details) return;
        const isHidden = details.hidden;
        details.hidden = !isHidden;
        btn.textContent = isHidden ? "▲ Less" : "▼ Details";
      });
    });
    list.querySelectorAll(".btn-mem-agent-approve").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const id = btn.dataset.id;
        if (!id) return;
        btn.disabled = true;
        try {
          const res = await fetchJSON(`/api/memory-agent/proposals/${encodeURIComponent(id)}/approve`, { method: "POST" });
          alert(res.ok ? res.message : "Error: " + res.message);
          loadMemoryAgentProposals();
          loadMemories();
          loadCircles();
          if (res.ok) loadEvents();
        } finally {
          btn.disabled = false;
        }
      });
    });
    list.querySelectorAll(".btn-mem-agent-reject").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const id = btn.dataset.id;
        if (!id) return;
        btn.disabled = true;
        try {
          const res = await fetchJSON(`/api/memory-agent/proposals/${encodeURIComponent(id)}/reject`, { method: "POST" });
          if (res.ok) loadMemoryAgentProposals();
        } finally {
          btn.disabled = false;
        }
      });
    });
    list.querySelectorAll(".btn-proposal-add-todo").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const title = btn.dataset.title || "";
        const date = btn.dataset.date || "";
        if (!title.trim()) return;
        btn.disabled = true;
        try {
          const res = await fetchJSON("/api/todos", {
            method: "POST",
            body: JSON.stringify({ content: title.trim(), due_date: date }),
          });
          if (res.ok) {
            btn.textContent = "Added ✓";
            loadNotesAndTodos();
          } else {
            btn.disabled = false;
            alert(res.error || "Failed to add to TODO.");
          }
        } catch (err) {
          btn.disabled = false;
          alert("Failed: " + (err.message || err));
        }
      });
    });
  } catch (e) {
    const container = document.getElementById("memory-agent-proposals");
    if (container) container.hidden = true;
  }
}

document.getElementById("btn-memory-agent-run")?.addEventListener("click", async () => {
  const btn = document.getElementById("btn-memory-agent-run");
  if (btn) btn.disabled = true;
  try {
    const data = await fetchJSON("/api/memory-agent/run", { method: "POST" });
    if (data.ok) {
      const s = data.summary || {};
      const total = Object.values(s).reduce((a, b) => a + b, 0);
      alert(`Proposed ${total} changes: add=${s.add || 0}, remove=${s.remove || 0}, event=${s.event_memory || 0}, consolidate=${s.consolidate || 0}, promote=${s.promote || 0}`);
      loadMemoryAgentProposals();
    } else {
      alert(data.message || "Run failed.");
    }
  } catch (e) {
    alert("Error: " + (e.message || e));
  } finally {
    if (btn) btn.disabled = false;
  }
});

document.getElementById("btn-events-agent-run")?.addEventListener("click", async () => {
  const btn = document.getElementById("btn-events-agent-run");
  if (btn) btn.disabled = true;
  try {
    const data = await fetchJSON("/api/events-agent/run", { method: "POST" });
    if (data.ok) {
      const s = data.summary || {};
      const events = s.event_memory || 0;
      const created = s.scheduled_created || 0;
      const parts = [];
      if (created) parts.push(`Created ${created} event(s) from scheduled templates`);
      if (events) parts.push(`Proposed ${events} event→memory changes`);
      alert(parts.length ? parts.join(". ") : "Nothing to process.");
      loadMemoryAgentProposals();
      loadEvents();
      loadScheduledTemplates();
    } else {
      alert(data.message || "Run failed.");
    }
  } catch (e) {
    alert("Error: " + (e.message || e));
  } finally {
    if (btn) btn.disabled = false;
  }
});

function renderIntegrationStatus(connected, capabilities, connectUrl, connectLabel) {
  if (connected) {
    const caps = capabilities?.length
      ? `<span class="integration-caps"> (${capabilities.join(", ")})</span>`
      : "";
    return `<span class="status-connected">✓ ${connectLabel} connected</span>${caps}`;
  }
  return `<a href="${connectUrl}" class="btn btn-primary">Connect ${connectLabel}</a>`;
}

async function loadAboutMe() {
  const el = document.getElementById("about-me-content");
  if (!el) return;
  try {
    const data = await fetchJSON("/api/about-me");
    el.value = data.content || "";
  } catch {
    el.value = "";
  }
}

document.getElementById("btn-about-me-save")?.addEventListener("click", async function () {
  const el = document.getElementById("about-me-content");
  if (!el) return;
  const btn = this;
  btn.disabled = true;
  try {
    await fetchJSON("/api/about-me", {
      method: "PUT",
      body: JSON.stringify({ content: el.value }),
    });
    btn.textContent = "Saved ✓";
    setTimeout(() => { btn.textContent = "Save"; }, 2000);
  } catch (e) {
    alert("Failed to save: " + (e.message || "unknown error"));
  } finally {
    btn.disabled = false;
  }
});

async function importAboutMeFromFile(file, endpoint) {
  if (!file || !file.name.toLowerCase().endsWith(".zip")) {
    alert("Please select a ZIP file from LinkedIn or Facebook data export.");
    return;
  }
  const contentEl = document.getElementById("about-me-content");
  if (!contentEl) return;
  const fd = new FormData();
  fd.append("file", file);
  try {
    const res = await fetch(API + endpoint, {
      method: "POST",
      body: fd,
      headers: {}, // Let browser set Content-Type for FormData
    });
    const data = await res.json();
    if (data.ok) {
      contentEl.value = data.content || "";
      loadAboutMe();
      alert("Imported successfully. Review and click Save if you want to keep changes.");
    } else {
      alert(data.message || "Import failed.");
    }
  } catch (e) {
    alert("Import failed: " + (e.message || "unknown error"));
  }
}

document.getElementById("about-me-linkedin-file")?.addEventListener("change", function () {
  const file = this.files?.[0];
  if (file) importAboutMeFromFile(file, "/api/about-me/import/linkedin");
  this.value = "";
});

document.getElementById("about-me-facebook-file")?.addEventListener("change", function () {
  const file = this.files?.[0];
  if (file) importAboutMeFromFile(file, "/api/about-me/import/facebook");
  this.value = "";
});

async function loadGoogleStatus() {
  const el = document.getElementById("google-status");
  const btn = document.getElementById("btn-disconnect-google");
  if (!el) return;
  try {
    const data = await fetchJSON("/api/integrations/google/status");
    if (data.connected) {
      el.innerHTML = renderIntegrationStatus(
        true,
        data.capabilities,
        "/api/integrations/google/authorize",
        "Google"
      );
      if (btn) btn.style.display = "inline-block";
    } else {
      el.innerHTML = renderIntegrationStatus(
        false,
        [],
        "/api/integrations/google/authorize",
        "Google"
      );
      if (btn) btn.style.display = "none";
    }
  } catch {
    el.innerHTML = '<a href="/api/integrations/google/authorize" class="btn btn-primary">Connect Google</a>';
    if (btn) btn.style.display = "none";
  }
}

async function loadYahooStatus() {
  const el = document.getElementById("yahoo-status");
  const btn = document.getElementById("btn-disconnect-yahoo");
  if (!el) return;
  try {
    const data = await fetchJSON("/api/integrations/yahoo/status");
    if (data.connected) {
      el.innerHTML = renderIntegrationStatus(
        true,
        data.capabilities,
        "/api/integrations/yahoo/authorize",
        "Yahoo Mail"
      );
      if (btn) btn.style.display = "inline-block";
    } else {
      el.innerHTML = renderIntegrationStatus(
        false,
        [],
        "/api/integrations/yahoo/authorize",
        "Yahoo Mail"
      );
      if (btn) btn.style.display = "none";
    }
  } catch {
    el.innerHTML = '<a href="/api/integrations/yahoo/authorize" class="btn btn-primary">Connect Yahoo Mail</a>';
    if (btn) btn.style.display = "none";
  }
}

async function loadSmsStatus() {
  const el = document.getElementById("sms-status");
  if (!el) return;
  try {
    const data = await fetchJSON("/api/integrations/twilio/status");
    if (data.connected) {
      const phone = data.phone_masked ? ` <span class="integration-caps">(${data.phone_masked})</span>` : "";
      el.innerHTML = `<span class="status-connected">✓ SMS (Twilio) connected</span>${phone}`;
    } else {
      el.innerHTML = '<span class="status-disconnected">SMS not configured</span>';
    }
  } catch {
    el.innerHTML = '<span class="status-disconnected">SMS not configured</span>';
  }
}

document.getElementById("btn-disconnect-google")?.addEventListener("click", async function () {
  if (!confirm("Disconnect Google? Woody will lose access to Gmail and Calendar until you reconnect.")) return;
  try {
    const res = await fetch("/api/integrations/google", { method: "DELETE" });
    const data = await res.json();
    if (data.ok) {
      loadGoogleStatus();
    } else {
      alert(data.message || "Failed to disconnect.");
    }
  } catch (e) {
    alert("Failed to disconnect: " + (e.message || "unknown error"));
  }
});

document.getElementById("btn-disconnect-yahoo")?.addEventListener("click", async function () {
  if (!confirm("Disconnect Yahoo? Woody will lose access to Yahoo Mail until you reconnect.")) return;
  try {
    const res = await fetch("/api/integrations/yahoo", { method: "DELETE" });
    const data = await res.json();
    if (data.ok) {
      loadYahooStatus();
    } else {
      alert(data.message || "Failed to disconnect.");
    }
  } catch (e) {
    alert("Failed to disconnect: " + (e.message || "unknown error"));
  }
});

document.getElementById("btn-run-communications")?.addEventListener("click", async function () {
  const btn = document.getElementById("btn-run-communications");
  if (btn) btn.disabled = true;
  try {
    const data = await fetchJSON("/api/communications/run", { method: "POST" });
    alert(data.ok ? data.message : "Error: " + data.message);
    if (data.ok && (data.circle_proposals || data.event_proposals)) {
      loadMemoryAgentProposals();
      loadContacts();
      loadCircles();
      loadEvents();
    }
  } catch (e) {
    alert("Error: " + (e.message || e));
  } finally {
    if (btn) btn.disabled = false;
  }
});

async function loadScheduledTemplates() {
  try {
    const items = await fetchJSON("/api/scheduled-templates");
    const list = document.getElementById("list-scheduled-templates");
    if (!list) return;
    list.innerHTML = Array.isArray(items) && items.length
      ? items.map((t) => `
          <li>
            <p class="item-desc">${escapeHtml(t.title || "")} <span class="badge">${escapeHtml(t.recurrence || "")}</span> (anchor: ${t.anchor_date})</p>
            <div class="item-actions">
              <button class="btn btn-danger" data-delete-template="${t.id}">Remove</button>
            </div>
          </li>
        `).join("")
      : '<li class="empty">No scheduled templates. Add bills, inspections, birthdays above.</li>';
    list.querySelectorAll("[data-delete-template]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        await fetchJSON(`/api/scheduled-templates/${btn.dataset.deleteTemplate}`, { method: "DELETE" });
        loadScheduledTemplates();
        loadEvents();
      });
    });
  } catch (e) {
    const list = document.getElementById("list-scheduled-templates");
    if (list) list.innerHTML = '<li class="empty">Unable to load templates.</li>';
  }
}

async function loadWishlist() {
  try {
    const items = await fetchJSON("/api/wishlist");
    const list = document.getElementById("list-wishlist");
    if (!list) return;
    list.innerHTML = Array.isArray(items) && items.length
      ? items.map(renderWishlistItem).join("")
      : '<li class="empty">Nothing on the wishlist yet. Add something above or ask Woody.</li>';
    list.querySelectorAll("[data-fulfill-wishlist]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const id = btn.dataset.fulfillWishlist;
        if (!id) return;
        btn.disabled = true;
        try {
          const res = await fetchJSON(`/api/wishlist/${id}/fulfill`, { method: "POST" });
          if (res.ok) {
            loadWishlist();
            loadEvents();
            loadMemoryAgentProposals();
          } else {
            alert(res.error || "Failed to fulfill.");
          }
        } catch (e) {
          alert("Error: " + (e.message || e));
        } finally {
          btn.disabled = false;
        }
      });
    });
    list.querySelectorAll("[data-delete-wishlist]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        await fetchJSON(`/api/wishlist/${btn.dataset.deleteWishlist}`, { method: "DELETE" });
        loadWishlist();
      });
    });
  } catch (e) {
    const list = document.getElementById("list-wishlist");
    if (list) list.innerHTML = '<li class="empty">Unable to load wishlist.</li>';
  }
}

loadEvents();
loadDecisions();
loadNotesAndTodos();
let currentUserName = "Jack Wood";

async function loadCurrentUser() {
  try {
    const data = await fetchJSON("/api/me");
    currentUserName = data.user || "Jack Wood";
  } catch {
    currentUserName = "Jack Wood";
  }
}

async function loadAuthUser() {
  const el = document.getElementById("header-user");
  if (!el) return;
  try {
    const data = await fetch(API + "/api/auth/me", { credentials: "include" }).then((r) => r.json());
    if (data.logged_in && data.user) {
      const name = data.user.name || data.user.email || "User";
      const img = data.user.picture ? `<img src="${escapeAttr(data.user.picture)}" alt="" width="28" height="28">` : "";
      el.innerHTML = `${img}<span>${escapeHtml(name)}</span><a href="/api/auth/logout">Sign out</a>`;
    } else {
      el.innerHTML = "";
    }
  } catch {
    el.innerHTML = "";
  }
}

loadCurrentUser().then(() => {
  loadChatHistory();
  loadPendingApprovals();
});
loadAuthUser();
loadContacts();
initContactsSearchAndCollapse();
loadPlaces();
loadCircles();
loadScheduledTemplates();
loadWishlist();
loadMemories();
loadMemoryAgentProposals();
loadOtelTraces();
loadAboutMe();
loadGoogleStatus();
loadYahooStatus();
loadSmsStatus();

// --- Chat ---
async function loadChatHistory() {
  try {
    const data = await fetchJSON("/api/chat/history");
    const container = document.getElementById("chat-messages");
    if (!container) return;
    const msgs = data.messages || [];
    container.innerHTML = msgs.length
      ? msgs.map((m) => {
          const role = m.role === "user" ? currentUserName : "Woody";
          return `<div class="chat-message ${m.role}"><span class="role">${escapeHtml(role)}</span>${escapeHtml(m.content || "")}</div>`;
        }).join("")
      : '<div class="empty">No messages yet. Ask Woody to add an event, remember something, or list your circles.</div>';
    container.scrollTop = container.scrollHeight;
  } catch (e) {
    const container = document.getElementById("chat-messages");
    if (container) container.innerHTML = '<div class="empty">Unable to load chat.</div>';
  }
}

function appendChatMessage(role, content) {
  const container = document.getElementById("chat-messages");
  const empty = container?.querySelector(".empty");
  if (empty) empty.remove();
  if (!container) return;
  const div = document.createElement("div");
  div.className = `chat-message ${role}`;
  div.innerHTML = `<span class="role">${role === "user" ? currentUserName : "Woody"}</span>${escapeHtml(content)}`;
  container.appendChild(div);
  container.scrollTop = container.scrollHeight;
}

document.getElementById("form-chat")?.addEventListener("submit", async (e) => {
  e.preventDefault();
  const input = document.getElementById("chat-input");
  const msg = input?.value?.trim();
  if (!msg) return;
  input.value = "";
  appendChatMessage("user", msg);
  showChatThinking(true);

  try {
    const data = await fetchJSON("/api/chat", {
      method: "POST",
      body: JSON.stringify({ message: msg }),
    });
    showChatThinking(false);
    appendChatMessage("assistant", data.response || "(No response)");
    loadChatHistory();
  } catch (err) {
    showChatThinking(false);
    appendChatMessage("assistant", "Error: " + (err.message || err));
  }
});

const CHAT_THINKING_PHRASES = [
  "Thinking…",
  "Working on it…",
  "Let me check…",
  "One moment…",
  "Processing…",
  "Gathering my thoughts…",
  "On it…",
  "Pondering…",
  "Checking my memories…",
  "Figuring it out…",
  "Hold on…",
  "Almost there…",
];

function showChatThinking(show) {
  let el = document.getElementById("chat-thinking");
  if (show) {
    const container = document.getElementById("chat-messages");
    if (!container) return;
    const phrase = CHAT_THINKING_PHRASES[Math.floor(Math.random() * CHAT_THINKING_PHRASES.length)];
    if (el) {
      el.querySelector(".chat-thinking-text").textContent = phrase;
      el.hidden = false;
    } else {
      el = document.createElement("div");
      el.id = "chat-thinking";
      el.className = "chat-message assistant chat-thinking";
      el.innerHTML = `<span class="role">Woody</span><span class="chat-thinking-text">${phrase}</span>`;
      container.appendChild(el);
    }
    container.scrollTop = container.scrollHeight;
  } else if (el) {
    el.remove();
  }
}

document.getElementById("btn-chat-approve")?.addEventListener("click", async () => {
  if (!pendingApprovalId) return;
  const approveEl = document.getElementById("chat-approve");
  const btn = document.getElementById("btn-chat-approve");
  if (btn) btn.disabled = true;
  showChatThinking(true);
  try {
    const body = { approval_id: pendingApprovalId };
    if (pendingApprovalDbPath) body.db_path = pendingApprovalDbPath;
    const data = await fetchJSON("/api/approvals/approve", {
      method: "POST",
      body: JSON.stringify(body),
    });
    showChatThinking(false);
    appendChatMessage("assistant", data.ok ? data.message : "Error: " + data.message);
    if (approveEl) approveEl.hidden = true;
    pendingApprovalId = null;
    pendingApprovalDbPath = null;
    loadPendingApprovals();
  } catch (err) {
    showChatThinking(false);
    appendChatMessage("assistant", "Error: " + (err.message || err));
  } finally {
    if (btn) btn.disabled = false;
  }
});

// Auto-refresh pending approvals every 60s (expire old ones)
setInterval(loadPendingApprovals, 60000);

document.getElementById("btn-approve-all")?.addEventListener("click", async function () {
  const btn = this;
  btn.disabled = true;
  try {
    const res = await fetchJSON("/api/approvals/approve-all", { method: "POST" });
    if (res.ok && res.count > 0) {
      appendChatMessage("assistant", `Approved ${res.count} action(s).`);
      loadPendingApprovals();
      loadChatHistory();
    } else if (res.ok) {
      appendChatMessage("assistant", "No pending approvals.");
    } else {
      alert(res.message || "Approve all failed.");
    }
  } catch (e) {
    alert("Error: " + (e.message || e));
  } finally {
    btn.disabled = false;
  }
});

document.getElementById("btn-reject-all")?.addEventListener("click", async function () {
  const btn = this;
  btn.disabled = true;
  try {
    const res = await fetchJSON("/api/approvals/reject-all", { method: "POST" });
    if (res.ok && res.count > 0) {
      appendChatMessage("assistant", `Rejected ${res.count} action(s).`);
      loadPendingApprovals();
      loadChatHistory();
    } else if (res.ok) {
      appendChatMessage("assistant", "No pending approvals.");
    } else {
      alert(res.message || "Reject all failed.");
    }
  } catch (e) {
    alert("Error: " + (e.message || e));
  } finally {
    btn.disabled = false;
  }
});

document.getElementById("btn-proposals-approve-all")?.addEventListener("click", async function () {
  const btn = this;
  const origText = btn.textContent;
  btn.disabled = true;
  btn.textContent = "Approving…";
  try {
    const res = await fetchJSON("/api/memory-agent/proposals/approve-all", { method: "POST" });
    if (res.ok && (res.count ?? 0) > 0) {
      loadMemoryAgentProposals();
      loadMemories();
      loadCircles();
      loadEvents();
      btn.textContent = `Approved ${res.count}`;
      setTimeout(() => { btn.textContent = origText; }, 1500);
    } else if (res.ok) {
      btn.textContent = "No pending";
      setTimeout(() => { btn.textContent = origText; }, 1500);
    } else {
      btn.textContent = origText;
      alert(res.message || "Approve all failed.");
    }
  } catch (e) {
    btn.textContent = origText;
    alert("Error: " + (e.message || e));
  } finally {
    btn.disabled = false;
    if (btn.textContent === "Approving…") btn.textContent = origText;
  }
});

document.getElementById("btn-proposals-reject-all")?.addEventListener("click", async function () {
  const btn = this;
  const origText = btn.textContent;
  btn.disabled = true;
  btn.textContent = "Rejecting…";
  try {
    const res = await fetchJSON("/api/memory-agent/proposals/reject-all", { method: "POST" });
    if (res.ok && (res.count ?? 0) > 0) {
      loadMemoryAgentProposals();
      btn.textContent = `Rejected ${res.count}`;
      setTimeout(() => { btn.textContent = origText; }, 1500);
    } else if (res.ok) {
      btn.textContent = "No pending";
      setTimeout(() => { btn.textContent = origText; }, 1500);
    } else {
      btn.textContent = origText;
      alert(res.message || "Reject all failed.");
    }
  } catch (e) {
    btn.textContent = origText;
    alert("Error: " + (e.message || e));
  } finally {
    btn.disabled = false;
    if (btn.textContent === "Rejecting…") btn.textContent = origText;
  }
});

// Auto-refresh Otel traces every 5s
setInterval(loadOtelTraces, 5000);
