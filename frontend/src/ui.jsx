import React, { useEffect, useRef, useId } from "react";
import { X, Download, Printer } from "lucide-react";
export const labels = {
  active: "Aktif",
  ending: "Bitiyor",
  frozen: "Dondurulmuş",
  expired: "Süresi dolmuş",
  pending: "Başlamamış",
  cancelled: "İptal",
  inactive: "Pasif",
  blocked: "Engelli",
  none: "Üyelik yok",
  confirmed: "Tamamlandı",
  granted: "Sensör bekleniyor",
  rejected: "Reddedildi",
  online: "Çevrimiçi",
  offline: "Çevrimdışı",
  booked: "Kayıtlı",
  waiting: "Bekleme listesi",
  attended: "Katıldı",
  cash: "Nakit",
  pos: "POS",
  bank: "Havale / EFT",
  mixed: "Karma",
  lost: "Kayıp",
  available: "Boş / Kullanıma hazır",
};
export const methods = ["cash", "pos", "bank", "mixed"].map((value) => ({
  value,
  label: labels[value],
}));
export function Badge({ status, children }) {
  return (
    <span className={`badge ${status}`}>
      {children || labels[status] || status}
    </span>
  );
}
export function Button({ icon: Icon, children, tone = "secondary", ...props }) {
  return (
    <button className={`button ${tone}`} {...props}>
      {Icon && <Icon size={17} />}
      {children}
    </button>
  );
}
export function IconButton({ icon: Icon, label, ...props }) {
  return (
    <button className="icon-button" title={label} aria-label={label} {...props}>
      <Icon size={18} />
    </button>
  );
}
export function Avatar({ member, size = "" }) {
  return member.photo ? (
    <img className={`avatar ${size}`} src={member.photo} alt={member.name} />
  ) : (
    <span className={`avatar ${size}`}>
      {member.name
        .split(" ")
        .map((part) => part[0])
        .slice(0, 2)
        .join("")}
    </span>
  );
}
export function Empty({ children = "Gösterilecek kayıt yok." }) {
  return <p className="empty-state">{children}</p>;
}
export function Table({ headers, children }) {
  return (
    <div className="table-scroll">
      <table className="data-table">
        <thead>
          <tr>
            {headers.map((header) => (
              <th key={header}>{header}</th>
            ))}
          </tr>
        </thead>
        <tbody>{children}</tbody>
      </table>
    </div>
  );
}
export function Field({ label, children }) {
  const id = useId();
  const controls = React.Children.map(children, (child) =>
    React.isValidElement(child) &&
    ["input", "select", "textarea"].includes(child.type)
      ? React.cloneElement(child, { "aria-labelledby": id })
      : child,
  );
  return (
    <label className="field">
      <span id={id}>{label}</span>
      {controls}
    </label>
  );
}
export function Metric({ icon: Icon, label, value, detail, tone = "" }) {
  return (
    <div className={`metric ${tone}`}>
      <div className="metric-label">
        <span>{label}</span>
        <Icon size={18} />
      </div>
      <strong>{value}</strong>
      {detail && <small>{detail}</small>}
    </div>
  );
}
export function Dialog({ title, onClose, children }) {
  const ref = useRef(null);
  useEffect(() => {
    const previous = document.activeElement;
    ref.current?.querySelector("input, select, textarea, button")?.focus();
    const handler = (event) => {
      if (event.key === "Escape") onClose();
      if (event.key === "Tab") {
        const focusable = [
          ...ref.current.querySelectorAll(
            'button, input, select, textarea, [tabindex="0"]',
          ),
        ].filter((item) => !item.disabled);
        const first = focusable[0],
          last = focusable.at(-1);
        if (event.shiftKey && document.activeElement === first) {
          event.preventDefault();
          last.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault();
          first.focus();
        }
      }
    };
    document.addEventListener("keydown", handler);
    return () => {
      document.removeEventListener("keydown", handler);
      previous?.focus();
    };
  }, []);
  return (
    <div
      className="modal-backdrop"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <section
        ref={ref}
        className="modal"
        role="dialog"
        aria-modal="true"
        aria-label={title}
      >
        <header>
          <h2>{title}</h2>
          <IconButton icon={X} label="Kapat" onClick={onClose} />
        </header>
        {children}
      </section>
    </div>
  );
}
export function ActionForm({
  title,
  fields,
  initial = {},
  onClose,
  onSave,
  children,
}) {
  return (
    <Dialog title={title} onClose={onClose}>
      <form
        onSubmit={async (event) => {
          event.preventDefault();
          const form = event.currentTarget,
            data = new FormData(form),
            values = { ...initial };
          fields.forEach((field) => {
            values[field.name] =
              field.type === "checkbox"
                ? form.elements.namedItem(field.name).checked
                : data.get(field.name);
          });
          if ((await onSave(values))?.ok) onClose();
        }}
      >
        <div className="form-grid">
          {fields.map((field) => (
            <Field label={field.label} key={field.name}>
              {field.options ? (
                <select
                  name={field.name}
                  defaultValue={initial[field.name] ?? field.defaultValue}
                  required={field.required !== false}
                >
                  {field.options.map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </select>
              ) : field.type === "textarea" ? (
                <textarea
                  name={field.name}
                  defaultValue={initial[field.name] || ""}
                  required={field.required !== false}
                />
              ) : (
                <input
                  name={field.name}
                  type={field.type || "text"}
                  defaultValue={
                    field.type === "checkbox"
                      ? undefined
                      : (initial[field.name] ?? field.defaultValue ?? "")
                  }
                  defaultChecked={
                    field.type === "checkbox"
                      ? (initial[field.name] ?? field.defaultValue)
                      : undefined
                  }
                  min={field.min}
                  max={field.max}
                  step={field.step}
                  required={field.required !== false}
                />
              )}
            </Field>
          ))}
        </div>
        {children}
        <footer className="form-footer">
          <Button onClick={onClose} type="button">
            Vazgeç
          </Button>
          <Button tone="primary" type="submit">
            Kaydet
          </Button>
        </footer>
      </form>
    </Dialog>
  );
}
export function exportCsv(name, headers, rows) {
  const safe = (value) => {
    const text = String(value ?? "");
    return /^[=+@\-\t\r]/.test(text) ? `'${text}` : text;
  };
  const content =
    "\uFEFF" +
    [headers, ...rows]
      .map((row) =>
        row.map((value) => `"${safe(value).replaceAll('"', '""')}"`).join(";"),
      )
      .join("\r\n");
  const url = URL.createObjectURL(
    new Blob([content], { type: "text/csv;charset=utf-8;" }),
  );
  const link = document.createElement("a");
  link.href = url;
  link.download = `${name}.csv`;
  link.click();
  URL.revokeObjectURL(url);
}
export function ExportButtons({ onExport }) {
  return (
    <div className="button-group">
      <IconButton icon={Download} label="CSV indir" onClick={onExport} />
      <IconButton
        icon={Printer}
        label="Yazdır / PDF"
        onClick={() => window.print()}
      />
    </div>
  );
}
