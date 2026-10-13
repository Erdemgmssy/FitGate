import React, { useState, useEffect } from "react";
import { Save, X } from "lucide-react";
import { Dialog, Button } from "./ui";
import { money } from "./attendance.mjs";
import { planDuration } from "./plan-rules.mjs";

export function PricingSettings({ plans, employees, onSave }) {
  const [prices, setPrices] = useState(plans);
  const [rates, setRates] = useState(
    Object.fromEntries(
      employees
        .filter((employee) => employee.type === "hourly")
        .map((employee) => [employee.id, employee.hourlyRate]),
    ),
  );
  const [saved, setSaved] = useState(false);
  const [confirm, setConfirm] = useState(false),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  const dirty =
    prices.some(
      (p) =>
        Number(p.price) !== Number(plans.find((x) => x.id === p.id)?.price),
    ) ||
    employees
      .filter((e) => e.type === "hourly")
      .some((e) => Number(rates[e.id]) !== Number(e.hourlyRate));
  async function save() {
    setBusy(true);
    setError("");
    try {
      const result = await onSave(
        prices.map((p) => ({ ...p, price: String(p.price) })),
        Object.fromEntries(
          Object.entries(rates).map(([id, rate]) => [id, String(rate)]),
        ),
        true,
      );
      setSaved(Boolean(result?.ok));
      if (result?.ok) setConfirm(false);
      else setError(result?.message || "Fiyatlar kaydedilemedi.");
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }
  useEffect(() => {
    if (saved) setPrices(plans);
  }, [plans, saved]);
  return (
    <form
      className="page-grid"
      onSubmit={(event) => {
        event.preventDefault();
        setConfirm(true);
      }}
    >
      <div className="content-grid two-columns">
        <section className="panel">
          <div className="panel-header">
            <h2>Paket Fiyatları</h2>
          </div>
          {prices.map((plan) => (
            <label className="price-row" key={plan.id}>
              <span>
                <strong>{plan.name}</strong>
                <small>{planDuration(plan)}</small>
              </span>
              <span className="price-input">
                <input
                  aria-label={`${plan.name} fiyat`}
                  type="number"
                  required
                  min="0"
                  step="0.01"
                  value={plan.price}
                  onChange={(event) => {
                    setPrices((current) =>
                      current.map((item) =>
                        item.id === plan.id
                          ? { ...item, price: event.target.value }
                          : item,
                      ),
                    );
                    setSaved(false);
                  }}
                />
                TL
              </span>
            </label>
          ))}
        </section>
        <section className="panel">
          <div className="panel-header">
            <h2>Saatlik Çalışan Ücretleri</h2>
          </div>
          {employees
            .filter((employee) => employee.type === "hourly")
            .map((employee) => (
              <label className="price-row" key={employee.id}>
                <strong>{employee.name}</strong>
                <span className="price-input">
                  <input
                    aria-label={`${employee.name} saatlik ücret`}
                    type="number"
                    min="0"
                    step="0.01"
                    required
                    value={rates[employee.id] ?? employee.hourlyRate}
                    onChange={(event) => {
                      setRates((current) => ({
                        ...current,
                        [employee.id]: event.target.value,
                      }));
                      setSaved(false);
                    }}
                  />
                  TL / sa
                </span>
              </label>
            ))}
        </section>
      </div>
      <div className="save-row">
        <label className="check-field">
          <input name="confirmed" type="checkbox" required />
          Fiyat ve ücret değişikliklerini onaylıyorum
        </label>
        <button
          className="primary-button"
          type="submit"
          disabled={!dirty || busy || saved}
        >
          <Save size={18} />
          Değişiklikleri kaydet
        </button>
        <Button
          icon={X}
          type="button"
          disabled={!dirty || busy}
          onClick={() => {
            setPrices(plans);
            setRates(
              Object.fromEntries(
                employees
                  .filter((e) => e.type === "hourly")
                  .map((e) => [e.id, e.hourlyRate]),
              ),
            );
            setSaved(false);
            setError("");
          }}
        >
          İptal
        </Button>
        {saved && (
          <p role="status" className="success-message">
            Fiyatlar ve saatlik ücretler güncellendi.
          </p>
        )}
      </div>
      {error && (
        <p role="alert" className="form-error">
          {error}
        </p>
      )}
      {confirm && (
        <Dialog
          title="Fiyat değişikliklerini onayla"
          onClose={() => !busy && setConfirm(false)}
        >
          <p>
            Yeni satışlar güncel fiyatı kullanır. Geçmiş satışlar ve üyelik
            koşulları değişmez. Saatlik ücretler personel mesai ücretidir.
          </p>
          {error && (
            <p role="alert" className="form-error">
              {error}
            </p>
          )}
          <div className="button-group">
            <Button type="button" icon={Save} disabled={busy} onClick={save}>
              Onayla ve kaydet
            </Button>
            <Button
              type="button"
              icon={X}
              disabled={busy}
              onClick={() => setConfirm(false)}
            >
              Vazgeç
            </Button>
          </div>
        </Dialog>
      )}
    </form>
  );
}
