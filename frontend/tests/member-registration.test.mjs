import test from "node:test";
import assert from "node:assert/strict";
import { normalizedPhone, validateMember } from "../src/member-validation.mjs";

test("telephone prefix and formatting normalize to the same Turkish number", () => {
  for (const phone of [
    "0532 999 88 77",
    "+90 (532) 999-88-77",
    "00905329998877",
    "5329998877",
  ])
    assert.equal(normalizedPhone(phone), "05329998877");
  assert.equal(normalizedPhone("+44 7911 123456"), "447911123456");
});
test("invalid and repeated-digit phones are rejected", () => {
  for (const phone of [
    "123",
    "abc05329998877",
    "00000000000",
    "+90 532 999 88 77 ext 1",
    "1".repeat(16),
  ])
    assert.throws(() => normalizedPhone(phone));
});
test("member fields stay optional except name and phone", () => {
  const values = validateMember({ name: " Test ", phone: "05329998877" }, []);
  assert.equal(values.name, "Test");
  assert.equal(values.email, "");
  assert.equal(values.planId, undefined);
  assert.equal(values.uid, undefined);
  assert.throws(() => validateMember({ name: " ", phone: "05329998877" }, []));
});
test("duplicate email and phone are rejected while editing the same member is allowed", () => {
  const members = [
    {
      id: "1",
      name: "Existing",
      phone: "05329998877",
      email: "member@example.com",
    },
  ];
  assert.throws(() =>
    validateMember({ name: "Other", phone: "+905329998877" }, members),
  );
  assert.throws(() =>
    validateMember(
      { name: "Other", phone: "05551112233", email: " MEMBER@EXAMPLE.COM " },
      members,
    ),
  );
  assert.equal(
    validateMember(
      { name: "Edit", phone: "+905329998877", email: " MEMBER@EXAMPLE.COM " },
      members,
      "1",
    ).email,
    "member@example.com",
  );
});
test("emergency telephone and email formats are validated", () => {
  assert.throws(() =>
    validateMember(
      { name: "Test", phone: "05329998877", emergencyPhone: "123" },
      [],
    ),
  );
  assert.throws(() =>
    validateMember({ name: "Test", phone: "05329998877", email: "bad" }, []),
  );
});
test("legacy duplicate email does not block editing unrelated member details", () => {
  const members = [
    { id: "1", phone: "05329998877", email: "member@example.com" },
    { id: "2", phone: "05551112233", email: "member@example.com" },
  ];
  assert.equal(
    validateMember(
      { name: "Updated", phone: "05329998877", email: "member@example.com" },
      members,
      "1",
    ).name,
    "Updated",
  );
  assert.throws(() =>
    validateMember(
      { name: "New", phone: "05552223344", email: "member@example.com" },
      members,
    ),
  );
});
