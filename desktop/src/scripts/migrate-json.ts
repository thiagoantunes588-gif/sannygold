import bcrypt from "bcryptjs";
import { Prisma, UserStatus } from "@prisma/client";
import { existsSync, mkdirSync, readdirSync, readFileSync, writeFileSync } from "node:fs";
import { basename, dirname, join, resolve } from "node:path";
import { randomBytes } from "node:crypto";
import { prisma } from "../backend/prisma";
import { roleFromInput } from "../backend/permissions";

type JsonRecord = Record<string, unknown>;

type MigrationReport = {
  startedAt: string;
  finishedAt?: string;
  dataDir: string;
  imported: Record<string, number>;
  ignored: string[];
  warnings: string[];
};

function argValue(name: string): string | undefined {
  const index = process.argv.indexOf(name);
  if (index >= 0 && process.argv[index + 1]) return process.argv[index + 1];
  return undefined;
}

function readJson(filePath: string): unknown {
  return JSON.parse(readFileSync(filePath, "utf-8"));
}

function jsonInput(value: unknown): Prisma.InputJsonValue {
  return JSON.parse(JSON.stringify(value)) as Prisma.InputJsonValue;
}

function asArray(payload: unknown): JsonRecord[] {
  return Array.isArray(payload) ? payload.filter((item): item is JsonRecord => Boolean(item && typeof item === "object" && !Array.isArray(item))) : [];
}

function text(value: unknown): string {
  return String(value || "").trim();
}

function numberOrNull(value: unknown): number | null {
  if (value === null || value === undefined || value === "") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function dateOrNull(value: unknown): Date | null {
  const raw = text(value);
  if (!raw) return null;
  const parsed = new Date(raw);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}

function legacyId(record: JsonRecord, fields: string[], fallbackPrefix: string, index: number): string {
  for (const field of fields) {
    const value = text(record[field]);
    if (value) return value;
  }
  return `${fallbackPrefix}-${index + 1}`;
}

async function importUsers(dataDir: string, report: MigrationReport): Promise<void> {
  const filePath = join(dataDir, "users.json");
  if (!existsSync(filePath)) return;
  const records = asArray(readJson(filePath));
  const disabledPassword = await bcrypt.hash(randomBytes(24).toString("base64url"), 12);

  for (let index = 0; index < records.length; index += 1) {
    const record = records[index];
    const email = text(record.email).toLowerCase();
    if (!email) {
      report.warnings.push(`users.json item ${index + 1}: ignorado sem email.`);
      continue;
    }
    await prisma.user.upsert({
      where: { email },
      create: {
        id: legacyId(record, ["id", "user_id"], "USR", index),
        name: text(record.nome || record.name || email),
        login: text(record.login || record.username || email).toLowerCase(),
        email,
        role: roleFromInput(text(record.role)),
        status: text(record.status).toLowerCase() === "inativo" ? UserStatus.INATIVO : UserStatus.ATIVO,
        mustChangePassword: true,
        passwordHash: disabledPassword,
        legacyPasswordHash: text(record.senha_hash),
      },
      update: {
        name: text(record.nome || record.name || email),
        login: text(record.login || record.username || email).toLowerCase(),
        role: roleFromInput(text(record.role)),
        legacyPasswordHash: text(record.senha_hash),
      },
    });
    report.imported.users = (report.imported.users || 0) + 1;
  }
}

async function importClients(dataDir: string, report: MigrationReport): Promise<void> {
  const filePath = join(dataDir, "clients.json");
  if (!existsSync(filePath)) return;
  const records = asArray(readJson(filePath));
  for (let index = 0; index < records.length; index += 1) {
    const record = records[index];
    const id = legacyId(record, ["client_id", "id"], "CLI", index);
    const customerName = text(record.customer_name || record.name || record.customerName);
    if (!customerName) {
      report.warnings.push(`clients.json item ${index + 1}: ignorado sem nome.`);
      continue;
    }
    await prisma.client.upsert({
      where: { legacyId: id },
      create: {
        legacyId: id,
        customerName,
        contactName: text(record.contact_name),
        cpfCnpj: text(record.cpf_cnpj),
        email: text(record.email),
        phone: text(record.phone || record.telefone),
        address: text(record.address),
        lat: numberOrNull(record.lat),
        lng: numberOrNull(record.lng),
        payload: jsonInput(record),
      },
      update: {
        customerName,
        contactName: text(record.contact_name),
        cpfCnpj: text(record.cpf_cnpj),
        email: text(record.email),
        phone: text(record.phone || record.telefone),
        address: text(record.address),
        lat: numberOrNull(record.lat),
        lng: numberOrNull(record.lng),
        payload: jsonInput(record),
      },
    });
    report.imported.clients = (report.imported.clients || 0) + 1;
  }
}

async function importEvents(dataDir: string, report: MigrationReport): Promise<void> {
  const filePath = join(dataDir, "events.json");
  if (!existsSync(filePath)) return;
  const records = asArray(readJson(filePath));
  for (let index = 0; index < records.length; index += 1) {
    const record = records[index];
    const id = legacyId(record, ["event_id", "id"], "EVT", index);
    await prisma.event.upsert({
      where: { legacyId: id },
      create: {
        legacyId: id,
        title: text(record.title || record.name || id),
        eventDate: dateOrNull(record.event_date),
        status: text(record.status) || "planejado",
        notes: text(record.notes),
        payload: jsonInput(record),
      },
      update: {
        title: text(record.title || record.name || id),
        eventDate: dateOrNull(record.event_date),
        status: text(record.status) || "planejado",
        notes: text(record.notes),
        payload: jsonInput(record),
      },
    });
    report.imported.events = (report.imported.events || 0) + 1;
  }
}

async function importEquipment(dataDir: string, report: MigrationReport): Promise<void> {
  const filePath = join(dataDir, "equipment.json");
  if (!existsSync(filePath)) return;
  const records = asArray(readJson(filePath));
  for (let index = 0; index < records.length; index += 1) {
    const record = records[index];
    const id = legacyId(record, ["equipment_id", "id"], "EQ", index);
    await prisma.equipment.upsert({
      where: { legacyId: id },
      create: {
        legacyId: id,
        equipmentType: text(record.equipment_type || record.type || "Equipamento"),
        status: text(record.status || record.condition) || "disponivel",
        condition: text(record.condition),
        notes: text(record.notes),
        payload: jsonInput(record),
      },
      update: {
        equipmentType: text(record.equipment_type || record.type || "Equipamento"),
        status: text(record.status || record.condition) || "disponivel",
        condition: text(record.condition),
        notes: text(record.notes),
        payload: jsonInput(record),
      },
    });
    report.imported.equipment = (report.imported.equipment || 0) + 1;
  }
}

async function importVehicles(dataDir: string, report: MigrationReport): Promise<void> {
  const filePath = join(dataDir, "vehicles.json");
  if (!existsSync(filePath)) return;
  const records = asArray(readJson(filePath));
  for (let index = 0; index < records.length; index += 1) {
    const record = records[index];
    const id = legacyId(record, ["vehicle_id", "id", "plate"], "VEI", index);
    await prisma.vehicle.upsert({
      where: { legacyId: id },
      create: {
        legacyId: id,
        plate: text(record.plate),
        vehicleType: text(record.vehicle_type),
        model: text(record.model),
        driverName: text(record.driver_name || record.motorista),
        payload: jsonInput(record),
      },
      update: {
        plate: text(record.plate),
        vehicleType: text(record.vehicle_type),
        model: text(record.model),
        driverName: text(record.driver_name || record.motorista),
        payload: jsonInput(record),
      },
    });
    report.imported.vehicles = (report.imported.vehicles || 0) + 1;
  }
}

async function importFinancialEntries(dataDir: string, report: MigrationReport): Promise<void> {
  const filePath = join(dataDir, "financial_entries.json");
  if (!existsSync(filePath)) return;
  const records = asArray(readJson(filePath));
  for (let index = 0; index < records.length; index += 1) {
    const record = records[index];
    const id = legacyId(record, ["entry_id", "id"], "FIN", index);
    await prisma.financialEntry.upsert({
      where: { legacyId: id },
      create: {
        legacyId: id,
        entryType: text(record.entry_type || record.type || "lancamento"),
        category: text(record.category),
        description: text(record.description),
        amount: numberOrNull(record.amount) || 0,
        entryDate: dateOrNull(record.entry_date || record.date),
        status: text(record.status) || "aberto",
        payload: jsonInput(record),
      },
      update: {
        entryType: text(record.entry_type || record.type || "lancamento"),
        category: text(record.category),
        description: text(record.description),
        amount: numberOrNull(record.amount) || 0,
        entryDate: dateOrNull(record.entry_date || record.date),
        status: text(record.status) || "aberto",
        payload: jsonInput(record),
      },
    });
    report.imported.financialEntries = (report.imported.financialEntries || 0) + 1;
  }
}

async function importServiceOrders(dataDir: string, report: MigrationReport): Promise<void> {
  const filePath = join(dataDir, "service_orders.json");
  if (!existsSync(filePath)) return;
  const records = asArray(readJson(filePath));
  for (let index = 0; index < records.length; index += 1) {
    const record = records[index];
    const id = legacyId(record, ["service_order_id", "order_id", "id"], "OS", index);
    await prisma.serviceOrder.upsert({
      where: { legacyId: id },
      create: {
        legacyId: id,
        eventId: text(record.event_id),
        clientId: text(record.client_id),
        driverId: text(record.driver_id),
        status: text(record.status) || "aberta",
        scheduledAt: dateOrNull(record.scheduled_at || record.date),
        payload: jsonInput(record),
      },
      update: {
        eventId: text(record.event_id),
        clientId: text(record.client_id),
        driverId: text(record.driver_id),
        status: text(record.status) || "aberta",
        scheduledAt: dateOrNull(record.scheduled_at || record.date),
        payload: jsonInput(record),
      },
    });
    report.imported.serviceOrders = (report.imported.serviceOrders || 0) + 1;
  }
}

async function importGeneric(dataDir: string, report: MigrationReport): Promise<void> {
  const normalizedFiles = new Set([
    "users.json",
    "clients.json",
    "events.json",
    "equipment.json",
    "vehicles.json",
    "financial_entries.json",
    "service_orders.json",
  ]);

  for (const file of readdirSync(dataDir).filter((item) => item.endsWith(".json")).sort()) {
    if (normalizedFiles.has(file)) continue;
    const payload = readJson(join(dataDir, file));
    const entity = basename(file, ".json");
    const records = Array.isArray(payload) ? asArray(payload) : [{ id: entity, payload }];
    for (let index = 0; index < records.length; index += 1) {
      const record = records[index];
      const id = legacyId(record, ["id", `${entity}_id`, "created_at"], entity.toUpperCase(), index);
      await prisma.genericRecord.upsert({
        where: { entity_legacyId: { entity, legacyId: id } },
        create: {
          entity,
          legacyId: id,
          label: text(record.title || record.name || record.customer_name || record.created_at || id),
          payload: jsonInput(record),
        },
        update: {
          label: text(record.title || record.name || record.customer_name || record.created_at || id),
          payload: jsonInput(record),
        },
      });
      report.imported[entity] = (report.imported[entity] || 0) + 1;
    }
  }
}

async function main() {
  const dataDir = resolve(argValue("--data-dir") || join(process.cwd(), "..", "data"));
  const reportPath = resolve(argValue("--report") || join(process.cwd(), "..", "data", "migration_reports", "postgres-prisma-migration.json"));
  const report: MigrationReport = {
    startedAt: new Date().toISOString(),
    dataDir,
    imported: {},
    ignored: [],
    warnings: [],
  };

  if (!existsSync(dataDir)) {
    throw new Error(`Pasta de dados não encontrada: ${dataDir}`);
  }

  await importUsers(dataDir, report);
  await importClients(dataDir, report);
  await importEvents(dataDir, report);
  await importEquipment(dataDir, report);
  await importVehicles(dataDir, report);
  await importFinancialEntries(dataDir, report);
  await importServiceOrders(dataDir, report);
  await importGeneric(dataDir, report);

  report.finishedAt = new Date().toISOString();
  mkdirSync(dirname(reportPath), { recursive: true });
  writeFileSync(reportPath, JSON.stringify(report, null, 2));
  console.log(JSON.stringify(report, null, 2));
}

main()
  .catch((error) => {
    console.error(error);
    process.exitCode = 1;
  })
  .finally(async () => {
    await prisma.$disconnect();
  });
