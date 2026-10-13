export function normalizedPhone(value) {
  if (typeof value !== "string" || !/^\+?[0-9 ()\-.]+$/.test(value.trim()))
    throw new Error("Telefon biçimi geçersiz.");
  let digits = value.replace(/\D/g, "");
  if (value.trim().startsWith("00")) digits = digits.slice(2);
  if (digits.length < 10 || digits.length > 15 || new Set(digits).size === 1)
    throw new Error("Telefon 10–15 rakam içermeli.");
  if (digits.length === 12 && digits.startsWith("90"))
    digits = "0" + digits.slice(2);
  else if (digits.length === 10 && !value.trim().startsWith("+"))
    digits = "0" + digits;
  return digits;
}

export function validateMember(values, members, memberId) {
  const phone = normalizedPhone(values.phone);
  const email = (values.email || "").trim().toLowerCase();
  if (!values.name?.trim()) throw new Error("Ad soyad gerekli.");
  if (email && !/^[^\s@]+@[^\s@.]+(?:\.[^\s@.]+)+$/.test(email))
    throw new Error("E-posta biçimi geçersiz.");
  if (values.emergencyPhone?.trim()) normalizedPhone(values.emergencyPhone);
  const original = members.find((member) => member.id === memberId);
  let originalPhone;
  try {
    originalPhone = original ? normalizedPhone(original.phone) : null;
  } catch {
    originalPhone = null;
  }
  for (const member of members) {
    if (member.id === memberId) continue;
    let otherPhone;
    try {
      otherPhone = normalizedPhone(member.phone);
    } catch {
      otherPhone = null;
    }
    if ((!original || originalPhone !== phone) && otherPhone === phone)
      throw new Error("Bu telefonla kayıtlı üye var; mevcut üyeliği kullanın.");
    if (
      email &&
      (!original || original.email?.trim().toLowerCase() !== email) &&
      member.email?.trim().toLowerCase() === email
    )
      throw new Error(
        "Bu e-posta ile kayıtlı üye var; mevcut üyeliği kullanın.",
      );
  }
  return {
    ...values,
    name: values.name.trim(),
    phone: values.phone.trim(),
    email,
  };
}
