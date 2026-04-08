#!/usr/bin/env python3
"""Greedy route planner for small/medium daily logistics operations."""

from __future__ import annotations

import argparse
import csv
import json
import math
import textwrap
from dataclasses import dataclass, field
from pathlib import Path
from typing import List


@dataclass
class Delivery:
    id: str
    lat: float
    lng: float
    demand: int
    service_minutes: int
    customer_name: str = ""
    client_type: str = "avulso"
    equipment_type: str = ""
    equipment_quantity: int = 1
    equipment_number: str = ""
    priority: int = 3
    window_start: int = 8 * 60
    window_end: int = 18 * 60
    address: str = ""
    preferred_vehicle_id: str = ""


@dataclass
class Vehicle:
    id: str
    start_lat: float
    start_lng: float
    capacity: int
    vehicle_type: str = ""
    plate: str = ""
    model: str = ""
    max_stops: int = 999
    max_minutes: int = 600


@dataclass
class Stop:
    delivery_id: str
    customer_name: str
    client_type: str
    equipment_type: str
    equipment_quantity: int
    equipment_number: str
    address: str
    lat: float
    lng: float
    arrival_minute: int
    start_service_minute: int
    departure_minute: int
    travel_km: float


@dataclass
class RouteResult:
    vehicle_id: str
    stops: List[Stop] = field(default_factory=list)
    total_km: float = 0.0
    total_minutes: int = 0
    used_capacity: int = 0


def hhmm_to_minutes(value: str) -> int:
    hh, mm = value.split(":")
    return int(hh) * 60 + int(mm)


def minutes_to_hhmm(value: int) -> str:
    h = value // 60
    m = value % 60
    return f"{h:02d}:{m:02d}"


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dlat = p2 - p1
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlon / 2) ** 2
    return 2 * r * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def google_maps_place_url(lat: float, lng: float) -> str:
    return f"https://www.google.com/maps/search/?api=1&query={lat},{lng}"


def google_maps_directions_url(destination_lat: float, destination_lng: float) -> str:
    return (
        "https://www.google.com/maps/dir/?api=1"
        f"&destination={destination_lat},{destination_lng}&travelmode=driving"
    )


def load_deliveries(path: Path) -> List[Delivery]:
    deliveries: List[Delivery] = []
    seen = set()

    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        required = {"id", "lat", "lng", "demand", "service_minutes"}
        if not required.issubset(reader.fieldnames or []):
            raise ValueError(f"Missing required delivery columns: {sorted(required)}")

        for row in reader:
            item_id = (row.get("id") or "").strip()
            if not item_id:
                raise ValueError("Delivery id cannot be empty")
            if item_id in seen:
                raise ValueError(f"Duplicate delivery id: {item_id}")
            seen.add(item_id)

            demand = int(row["demand"])
            if demand <= 0:
                raise ValueError(f"Delivery demand must be > 0 for id={item_id}")

            window_start = hhmm_to_minutes((row.get("window_start") or "08:00").strip())
            window_end = hhmm_to_minutes((row.get("window_end") or "18:00").strip())
            if window_start >= window_end:
                raise ValueError(f"Invalid time window for id={item_id}")

            deliveries.append(
                Delivery(
                    id=item_id,
                    customer_name=(row.get("customer_name") or "").strip(),
                    client_type=(row.get("client_type") or "avulso").strip().lower(),
                    equipment_type=(row.get("equipment_type") or "").strip(),
                    equipment_quantity=int((row.get("equipment_quantity") or row["demand"]).strip()),
                    equipment_number=(row.get("equipment_number") or "").strip(),
                    address=(row.get("address") or "").strip(),
                    lat=float(row["lat"]),
                    lng=float(row["lng"]),
                    demand=demand,
                    service_minutes=int(row["service_minutes"]),
                    priority=int((row.get("priority") or "3").strip()),
                    window_start=window_start,
                    window_end=window_end,
                    preferred_vehicle_id=(row.get("preferred_vehicle_id") or "").strip(),
                )
            )

    deliveries.sort(key=lambda d: (d.priority, d.window_end, d.id))
    return deliveries


def load_vehicles(path: Path) -> List[Vehicle]:
    vehicles: List[Vehicle] = []
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        required = {"id", "start_lat", "start_lng", "capacity"}
        if not required.issubset(reader.fieldnames or []):
            raise ValueError(f"Missing required vehicle columns: {sorted(required)}")

        for row in reader:
            vehicles.append(
                Vehicle(
                    id=(row.get("id") or "").strip(),
                    start_lat=float(row["start_lat"]),
                    start_lng=float(row["start_lng"]),
                    capacity=int(row["capacity"]),
                    vehicle_type=(row.get("vehicle_type") or "").strip(),
                    plate=(row.get("plate") or "").strip(),
                    model=(row.get("model") or "").strip(),
                    max_stops=int((row.get("max_stops") or "999").strip()),
                    max_minutes=int((row.get("max_minutes") or "600").strip()),
                )
            )

    if not vehicles:
        raise ValueError("At least one vehicle is required")
    return vehicles


def best_vehicle_start_distance(delivery: Delivery, vehicles: List[Vehicle]) -> float:
    return min(
        haversine_km(vehicle.start_lat, vehicle.start_lng, delivery.lat, delivery.lng)
        for vehicle in vehicles
    )


def vehicle_start_affinity_km(delivery: Delivery, vehicle: Vehicle, vehicles: List[Vehicle]) -> float:
    vehicle_distance = haversine_km(vehicle.start_lat, vehicle.start_lng, delivery.lat, delivery.lng)
    best_distance = best_vehicle_start_distance(delivery, vehicles)
    return max(0.0, vehicle_distance - best_distance)


def pick_next_delivery(
    current_lat: float,
    current_lng: float,
    current_time: int,
    used_capacity: int,
    vehicle: Vehicle,
    pending: List[Delivery],
    speed_kmph: float,
    route_start_minute: int,
    vehicles: List[Vehicle],
):
    best = None
    best_score = float("inf")

    for delivery in pending:
        if delivery.preferred_vehicle_id and delivery.preferred_vehicle_id != vehicle.id:
            continue

        if used_capacity + delivery.demand > vehicle.capacity:
            continue

        travel_km = haversine_km(current_lat, current_lng, delivery.lat, delivery.lng)
        travel_min = int(round((travel_km / speed_kmph) * 60))
        arrival = current_time + travel_min
        service_start = max(arrival, delivery.window_start)
        wait_min = max(0, delivery.window_start - arrival)
        lateness_min = max(0, service_start - delivery.window_end)

        if service_start > delivery.window_end:
            continue

        departure = service_start + delivery.service_minutes
        if departure - route_start_minute > vehicle.max_minutes:
            continue

        # This score keeps the algorithm greedy and fast, while biasing it toward:
        # 1. nearby stops,
        # 2. event-window urgency,
        # 3. geographic grouping by vehicle depot/start position.
        urgency_min = max(0, delivery.window_end - arrival)
        urgency_penalty = 0 if urgency_min <= 120 else (urgency_min - 120) * 0.01
        depot_affinity_penalty = vehicle_start_affinity_km(delivery, vehicle, vehicles)
        priority_bonus = max(0, 4 - delivery.priority) * 1.5

        score = (
            travel_km * 1.0
            + wait_min * 0.08
            + lateness_min * 12.0
            + urgency_penalty
            + depot_affinity_penalty * 1.8
            - priority_bonus
        )
        if score < best_score:
            best_score = score
            best = (delivery, travel_km, arrival, service_start, departure)

    return best


def build_routes(deliveries: List[Delivery], vehicles: List[Vehicle], speed_kmph: float) -> tuple[List[RouteResult], List[Delivery]]:
    # Start by roughly grouping each stop toward the nearest vehicle base to reduce route overlap.
    pending = sorted(
        deliveries[:],
        key=lambda delivery: (
            delivery.priority,
            delivery.window_end,
            best_vehicle_start_distance(delivery, vehicles),
            delivery.id,
        ),
    )
    routes: List[RouteResult] = []

    for vehicle in vehicles:
        route = RouteResult(vehicle_id=vehicle.id)
        current_lat = vehicle.start_lat
        current_lng = vehicle.start_lng
        route_start_minute = 8 * 60
        current_time = route_start_minute

        while pending and len(route.stops) < vehicle.max_stops:
            candidate = pick_next_delivery(
                current_lat,
                current_lng,
                current_time,
                route.used_capacity,
                vehicle,
                pending,
                speed_kmph,
                route_start_minute,
                vehicles,
            )
            if not candidate:
                break

            delivery, travel_km, arrival, service_start, departure = candidate
            route.stops.append(
                Stop(
                    delivery_id=delivery.id,
                    customer_name=delivery.customer_name,
                    client_type=delivery.client_type,
                    equipment_type=delivery.equipment_type,
                    equipment_quantity=delivery.equipment_quantity,
                    equipment_number=delivery.equipment_number,
                    address=delivery.address,
                    lat=delivery.lat,
                    lng=delivery.lng,
                    arrival_minute=arrival,
                    start_service_minute=service_start,
                    departure_minute=departure,
                    travel_km=round(travel_km, 2),
                )
            )

            route.total_km += travel_km
            route.used_capacity += delivery.demand
            route.total_minutes = departure - route_start_minute
            current_lat, current_lng, current_time = delivery.lat, delivery.lng, departure
            pending = [d for d in pending if d.id != delivery.id]

        routes.append(route)

    return routes, pending


def serialize(routes: List[RouteResult], unassigned: List[Delivery], vehicles: List[Vehicle]) -> dict:
    routes_payload = []
    total_km = 0.0

    for route, vehicle in zip(routes, vehicles):
        capacity_pct = (route.used_capacity / vehicle.capacity * 100) if vehicle.capacity else 0.0
        routes_payload.append(
            {
                "vehicle_id": route.vehicle_id,
                "vehicle_type": vehicle.vehicle_type,
                "vehicle_plate": vehicle.plate,
                "vehicle_model": vehicle.model,
                "stops": [
                    {
                        "delivery_id": s.delivery_id,
                        "customer_name": s.customer_name,
                        "client_type": s.client_type,
                        "equipment_type": s.equipment_type,
                        "equipment_quantity": s.equipment_quantity,
                        "equipment_number": s.equipment_number,
                        "address": s.address,
                        "lat": s.lat,
                        "lng": s.lng,
                        "google_maps_url": google_maps_place_url(s.lat, s.lng),
                        "google_maps_directions_url": google_maps_directions_url(s.lat, s.lng),
                        "arrival": minutes_to_hhmm(s.arrival_minute),
                        "service_start": minutes_to_hhmm(s.start_service_minute),
                        "departure": minutes_to_hhmm(s.departure_minute),
                        "travel_km": s.travel_km,
                    }
                    for s in route.stops
                ],
                "distance_km": round(route.total_km, 2),
                "total_minutes": route.total_minutes,
                "used_capacity": route.used_capacity,
                "capacity": vehicle.capacity,
                "utilization_capacity_pct": round(capacity_pct, 1),
            }
        )
        total_km += route.total_km

    assigned = sum(len(r.stops) for r in routes)
    total = assigned + len(unassigned)

    return {
        "summary": {
            "total_deliveries": total,
            "assigned_deliveries": assigned,
            "unassigned_deliveries": len(unassigned),
            "assigned_ratio": round((assigned / total) if total else 0, 3),
            "total_distance_km": round(total_km, 2),
        },
        "routes": routes_payload,
        "unassigned": [
            {
                        "delivery_id": d.id,
                        "customer_name": d.customer_name,
                        "client_type": d.client_type,
                        "equipment_type": d.equipment_type,
                        "equipment_quantity": d.equipment_quantity,
                        "equipment_number": d.equipment_number,
                        "priority": d.priority,
                        "address": d.address,
                        "google_maps_url": google_maps_place_url(d.lat, d.lng),
                        "google_maps_directions_url": google_maps_directions_url(d.lat, d.lng),
                        "window_start": minutes_to_hhmm(d.window_start),
                        "window_end": minutes_to_hhmm(d.window_end),
                    }
            for d in unassigned
        ],
    }


def serialize_mobile(payload: dict) -> dict:
    mobile_routes = []

    for route in payload["routes"]:
        stops = route["stops"]
        next_stop = stops[0] if stops else None
        mobile_routes.append(
            {
                "vehicle_id": route["vehicle_id"],
                "next_stop": (
                    {
                        "vehicle_id": route["vehicle_id"],
                        "vehicle_type": route["vehicle_type"],
                        "vehicle_plate": route["vehicle_plate"],
                        "vehicle_model": route["vehicle_model"],
                        "delivery_id": next_stop["delivery_id"],
                        "customer_name": next_stop["customer_name"],
                        "client_type": next_stop["client_type"],
                        "equipment_type": next_stop["equipment_type"],
                        "equipment_quantity": next_stop["equipment_quantity"],
                        "equipment_number": next_stop["equipment_number"],
                        "address": next_stop["address"],
                        "lat": next_stop["lat"],
                        "lng": next_stop["lng"],
                        "google_maps_url": next_stop["google_maps_url"],
                        "google_maps_directions_url": next_stop["google_maps_directions_url"],
                        "arrival": next_stop["arrival"],
                    }
                    if next_stop
                    else None
                ),
                "stops": [
                    {
                        "vehicle_id": route["vehicle_id"],
                        "vehicle_type": route["vehicle_type"],
                        "vehicle_plate": route["vehicle_plate"],
                        "vehicle_model": route["vehicle_model"],
                        "delivery_id": stop["delivery_id"],
                        "customer_name": stop["customer_name"],
                        "client_type": stop["client_type"],
                        "equipment_type": stop["equipment_type"],
                        "equipment_quantity": stop["equipment_quantity"],
                        "equipment_number": stop["equipment_number"],
                        "address": stop["address"],
                        "lat": stop["lat"],
                        "lng": stop["lng"],
                        "google_maps_url": stop["google_maps_url"],
                        "google_maps_directions_url": stop["google_maps_directions_url"],
                        "arrival": stop["arrival"],
                        "departure": stop["departure"],
                    }
                    for stop in stops
                ],
                "distance_km": route["distance_km"],
                "total_minutes": route["total_minutes"],
            }
        )

    return {
        "summary": payload["summary"],
        "routes": mobile_routes,
        "unassigned": payload["unassigned"],
    }


def pdf_escape(text: str) -> str:
    cleaned = text.encode("ascii", "replace").decode("ascii")
    return cleaned.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def build_pdf_lines(payload: dict) -> List[str]:
    summary = payload["summary"]
    lines = [
        "Plano de Rotas",
        "",
        (
            f"Entregas: {summary['assigned_deliveries']}/{summary['total_deliveries']}  "
            f"Nao atribuidas: {summary['unassigned_deliveries']}  "
            f"Distancia total: {summary['total_distance_km']} km"
        ),
        "",
    ]

    for route in payload["routes"]:
        lines.append(
            f"Veiculo {route['vehicle_id']}  {route.get('vehicle_type') or 'Tipo n/d'}  "
            f"{route.get('vehicle_model') or 'Modelo n/d'}  Placa {route.get('vehicle_plate') or 'n/d'}  "
            f"Distancia {route['distance_km']} km  Tempo {route['total_minutes']} min"
        )

        for index, stop in enumerate(route["stops"], start=1):
            address = stop.get("address") or "Sem endereco"
            customer_name = stop.get("customer_name") or "Sem cliente"
            client_type = stop.get("client_type") or "avulso"
            equipment_type = stop.get("equipment_type") or "Equipamento"
            equipment_quantity = stop.get("equipment_quantity") or 1
            equipment_number = stop.get("equipment_number") or "-"
            stop_line = (
                f"{index}. {stop['delivery_id']}  Cliente {customer_name} ({client_type})  "
                f"{equipment_quantity}x {equipment_type}  Equip {equipment_number}  {address}  "
                f"Chegada {stop['arrival']}  Saida {stop['departure']}"
            )
            lines.extend(textwrap.wrap(stop_line, width=92) or [" "])

        if not route["stops"]:
            lines.append("Nenhuma parada atribuida.")
        lines.append("")

    if payload["unassigned"]:
        lines.append("Pendencias")
        for item in payload["unassigned"]:
            lines.append(
                f"- {item['delivery_id']} cliente {item.get('customer_name') or 'Sem cliente'} "
                f"({item.get('client_type') or 'avulso'}) "
                f"{item.get('equipment_quantity') or 1}x {item.get('equipment_type') or 'Equipamento'} "
                f"equip {item.get('equipment_number') or '-'} "
                f"{item.get('address') or 'Sem endereco'} prioridade {item['priority']} "
                f"janela {item['window_start']}-{item['window_end']}"
            )

    return lines


def estimate_text_width(text: str, font_size: float, bold: bool = False) -> float:
    factor = 0.57 if bold else 0.52
    return len(text) * font_size * factor


def fit_text_to_width(text: str, width: float, font_size: float, bold: bool = False) -> str:
    normalized = " ".join((text or "").split())
    if not normalized:
        return "-"
    if estimate_text_width(normalized, font_size, bold) <= width:
        return normalized
    ellipsis = "..."
    trimmed = normalized
    while trimmed and estimate_text_width(trimmed + ellipsis, font_size, bold) > width:
        trimmed = trimmed[:-1]
    return (trimmed.rstrip() + ellipsis) if trimmed else ellipsis


def build_pdf_document(objects: List[bytes]) -> bytes:
    pdf = bytearray(b"%PDF-1.4\n")
    offsets = [0]

    for object_id, obj in enumerate(objects, start=1):
        offsets.append(len(pdf))
        pdf.extend(f"{object_id} 0 obj\n".encode("ascii"))
        pdf.extend(obj)
        pdf.extend(b"\nendobj\n")

    xref_offset = len(pdf)
    pdf.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    pdf.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        pdf.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    pdf.extend(
        (
            f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref_offset}\n%%EOF\n"
        ).encode("ascii")
    )
    return bytes(pdf)


def write_driver_manifest_pdf(payload: dict, output_path: Path) -> None:
    page_width = 842
    page_height = 595
    margin_left = 24
    margin_right = 24
    margin_top = 24
    margin_bottom = 24
    content_width = page_width - margin_left - margin_right

    columns = [
        ("Data", 50),
        ("Cliente", 90),
        ("Contato", 62),
        ("CPF/CNPJ", 62),
        ("E-mail", 88),
        ("Local", 156),
        ("Equipamento", 70),
        ("Qtd", 26),
        ("Chegada", 44),
        ("Janela", 54),
        ("Status / Obs.", 92),
    ]

    pages: List[List[str]] = []
    page_commands: List[str] = []

    def new_page() -> tuple[List[str], float]:
        commands: List[str] = []
        y = margin_top
        commands.extend(
            [
                "0.87 0.95 0.80 rg",
                "0.87 0.95 0.80 RG",
                f"{margin_left:.2f} {page_height - y - 34:.2f} {content_width:.2f} 34 re",
                "B",
            ]
        )
        commands.extend(
            [
                "BT",
                "/F2 18 Tf",
                "0.16 0.26 0.16 rg",
                f"1 0 0 1 {margin_left + 14:.2f} {page_height - y - 22:.2f} Tm",
                f"({pdf_escape('Romaneio Operacional de Entregas')}) Tj",
                "ET",
            ]
        )
        subtitle_parts = [
            f"Data base {payload.get('operation_date') or '-'}",
            f"Gerado em {payload.get('generated_at') or '-'}",
            (
                f"Entregas {payload.get('summary', {}).get('assigned_deliveries', 0)}/"
                f"{payload.get('summary', {}).get('total_deliveries', 0)}"
            ),
        ]
        if payload.get("event_title"):
            subtitle_parts.insert(0, f"Evento {payload['event_title']}")
        commands.extend(
            [
                "BT",
                "/F1 9 Tf",
                "0.22 0.28 0.24 rg",
                f"1 0 0 1 {margin_left + 14:.2f} {page_height - y - 32:.2f} Tm",
                f"({pdf_escape('  |  '.join(subtitle_parts))}) Tj",
                "ET",
            ]
        )
        return commands, y + 48

    def add_rect(commands: List[str], x: float, y_top: float, width: float, height: float, *, fill_rgb=None, stroke_rgb=(0.66, 0.72, 0.66), line_width: float = 0.6) -> None:
        commands.append(f"{line_width:.2f} w")
        commands.append(f"{stroke_rgb[0]:.3f} {stroke_rgb[1]:.3f} {stroke_rgb[2]:.3f} RG")
        if fill_rgb is not None:
            commands.append(f"{fill_rgb[0]:.3f} {fill_rgb[1]:.3f} {fill_rgb[2]:.3f} rg")
        commands.append(f"{x:.2f} {page_height - y_top - height:.2f} {width:.2f} {height:.2f} re")
        commands.append("B" if fill_rgb is not None else "S")

    def add_text(commands: List[str], x: float, y_top: float, text: str, *, font: str = "F1", font_size: float = 8.0, rgb=(0.13, 0.16, 0.14)) -> None:
        commands.extend(
            [
                "BT",
                f"/{font} {font_size:.2f} Tf",
                f"{rgb[0]:.3f} {rgb[1]:.3f} {rgb[2]:.3f} rg",
                f"1 0 0 1 {x:.2f} {page_height - y_top:.2f} Tm",
                f"({pdf_escape(text)}) Tj",
                "ET",
            ]
        )

    def draw_table_header(commands: List[str], y_top: float) -> float:
        current_x = margin_left
        for label, width in columns:
            add_rect(commands, current_x, y_top, width, 22, fill_rgb=(0.70, 0.88, 0.52), stroke_rgb=(0.60, 0.74, 0.46))
            add_text(commands, current_x + 4, y_top + 14, fit_text_to_width(label, width - 8, 8, True), font="F2", font_size=8, rgb=(0.15, 0.25, 0.12))
            current_x += width
        return y_top + 22

    page_commands, current_y = new_page()

    for route in payload.get("routes", []):
        route_header_height = 28
        row_height = 24
        route_stops = route.get("stops") or []

        if current_y + route_header_height + 22 > page_height - margin_bottom:
            pages.append(page_commands)
            page_commands, current_y = new_page()

        add_rect(page_commands, margin_left, current_y, content_width, route_header_height, fill_rgb=(0.93, 0.96, 0.91), stroke_rgb=(0.74, 0.80, 0.72))
        route_line = (
            f"Veiculo {route.get('vehicle_id') or '-'}  |  {route.get('vehicle_type') or 'Tipo n/d'}  |  "
            f"{route.get('vehicle_model') or 'Modelo n/d'}  |  Placa {route.get('vehicle_plate') or 'n/d'}"
        )
        route_stats = (
            f"Paradas {len(route_stops)}  |  Distancia {route.get('distance_km', 0)} km  |  "
            f"Tempo {route.get('total_minutes', 0)} min"
        )
        add_text(page_commands, margin_left + 8, current_y + 11, fit_text_to_width(route_line, content_width - 16, 10, True), font="F2", font_size=10)
        add_text(page_commands, margin_left + 8, current_y + 22, fit_text_to_width(route_stats, content_width - 16, 8), font="F1", font_size=8, rgb=(0.29, 0.35, 0.30))
        current_y += route_header_height
        current_y = draw_table_header(page_commands, current_y)

        if not route_stops:
            add_rect(page_commands, margin_left, current_y, content_width, row_height, stroke_rgb=(0.82, 0.84, 0.82))
            add_text(page_commands, margin_left + 8, current_y + 15, "Nenhuma parada atribuida para este veiculo.", font_size=8)
            current_y += row_height + 10
            continue

        for stop in route_stops:
            if current_y + row_height > page_height - margin_bottom:
                pages.append(page_commands)
                page_commands, current_y = new_page()
                add_rect(page_commands, margin_left, current_y, content_width, route_header_height, fill_rgb=(0.93, 0.96, 0.91), stroke_rgb=(0.74, 0.80, 0.72))
                add_text(
                    page_commands,
                    margin_left + 8,
                    current_y + 11,
                    fit_text_to_width(
                        f"Veiculo {route.get('vehicle_id') or '-'}  |  continuacao",
                        content_width - 16,
                        10,
                        True,
                    ),
                    font="F2",
                    font_size=10,
                )
                add_text(page_commands, margin_left + 8, current_y + 22, fit_text_to_width(route_stats, content_width - 16, 8), font="F1", font_size=8, rgb=(0.29, 0.35, 0.30))
                current_y += route_header_height
                current_y = draw_table_header(page_commands, current_y)

            row_values = [
                stop.get("operation_date") or payload.get("operation_date") or "-",
                stop.get("customer_name") or "-",
                stop.get("contact_name") or "-",
                stop.get("cpf_cnpj") or "-",
                stop.get("email") or "-",
                stop.get("address") or "-",
                f"{stop.get('equipment_number') or '-'} {stop.get('equipment_type') or ''}".strip(),
                str(stop.get("equipment_quantity") or 1),
                stop.get("arrival") or "-",
                f"{stop.get('window_start') or '-'}-{stop.get('window_end') or '-'}",
                " | ".join(
                    part for part in [
                        stop.get("operational_status") or "",
                        stop.get("cycle_stage") or "",
                        stop.get("operation_notes") or "",
                    ] if part
                ) or "-",
            ]

            current_x = margin_left
            for (label, width), value in zip(columns, row_values):
                add_rect(page_commands, current_x, current_y, width, row_height, stroke_rgb=(0.82, 0.84, 0.82))
                add_text(
                    page_commands,
                    current_x + 3,
                    current_y + 15,
                    fit_text_to_width(str(value), width - 6, 7),
                    font_size=7,
                    rgb=(0.14, 0.16, 0.15),
                )
                current_x += width
            current_y += row_height

        current_y += 10

    if payload.get("unassigned"):
        if current_y + 30 > page_height - margin_bottom:
            pages.append(page_commands)
            page_commands, current_y = new_page()
        add_rect(page_commands, margin_left, current_y, content_width, 24, fill_rgb=(0.98, 0.92, 0.80), stroke_rgb=(0.84, 0.70, 0.48))
        add_text(page_commands, margin_left + 8, current_y + 16, "Pendencias nao atribuidas", font="F2", font_size=10, rgb=(0.35, 0.23, 0.08))
        current_y += 28
        for item in payload["unassigned"]:
            if current_y + 18 > page_height - margin_bottom:
                pages.append(page_commands)
                page_commands, current_y = new_page()
            text = (
                f"{item.get('delivery_id') or '-'}  |  {item.get('customer_name') or '-'}  |  "
                f"{item.get('address') or '-'}  |  janela {item.get('window_start') or '-'}-{item.get('window_end') or '-'}  |  "
                f"motivo {item.get('pending_reason_summary') or '-'}"
            )
            add_text(page_commands, margin_left + 4, current_y + 12, fit_text_to_width(text, content_width - 8, 8), font_size=8, rgb=(0.28, 0.20, 0.18))
            current_y += 18

    pages.append(page_commands)

    objects: List[bytes] = []
    page_object_ids = []
    font_regular_id = 3
    font_bold_id = 4

    for commands in pages:
        stream = "\n".join(commands).encode("ascii")
        content_object_id = len(objects) + 5
        page_object_id = len(objects) + 6
        objects.append(f"<< /Length {len(stream)} >>\nstream\n".encode("ascii") + stream + b"\nendstream")
        objects.append(
            (
                f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {page_width} {page_height}] "
                f"/Resources << /Font << /F1 {font_regular_id} 0 R /F2 {font_bold_id} 0 R >> >> "
                f"/Contents {content_object_id} 0 R >>"
            ).encode("ascii")
        )
        page_object_ids.append(page_object_id)

    kids = " ".join(f"{page_id} 0 R" for page_id in page_object_ids)
    catalog_object = b"<< /Type /Catalog /Pages 2 0 R >>"
    pages_object = f"<< /Type /Pages /Kids [{kids}] /Count {len(page_object_ids)} >>".encode("ascii")
    font_regular_object = b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"
    font_bold_object = b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>"

    pdf_bytes = build_pdf_document([catalog_object, pages_object, font_regular_object, font_bold_object, *objects])
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(pdf_bytes)


def write_simple_pdf(lines: List[str], output_path: Path) -> None:
    page_width = 595
    page_height = 842
    margin_left = 48
    margin_top = 58
    line_height = 16
    max_lines_per_page = 45

    pages = [lines[i : i + max_lines_per_page] for i in range(0, len(lines), max_lines_per_page)] or [[]]
    objects: List[bytes] = []

    font_object_id = 1
    page_object_ids = []

    for page_lines in pages:
        content_lines = ["BT", "/F1 11 Tf", f"{margin_left} {page_height - margin_top} Td"]
        first = True
        for line in page_lines:
            if first:
                content_lines.append(f"({pdf_escape(line)}) Tj")
                first = False
            else:
                content_lines.append(f"0 -{line_height} Td")
                content_lines.append(f"({pdf_escape(line)}) Tj")
        content_lines.append("ET")
        stream = "\n".join(content_lines).encode("ascii")
        content_object_id = len(objects) + 2
        page_object_id = len(objects) + 3
        objects.append(
            f"<< /Length {len(stream)} >>\nstream\n".encode("ascii") + stream + b"\nendstream"
        )
        objects.append(
            (
                f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {page_width} {page_height}] "
                f"/Resources << /Font << /F1 {font_object_id} 0 R >> >> /Contents {content_object_id} 0 R >>"
            ).encode("ascii")
        )
        page_object_ids.append(page_object_id)

    kids = " ".join(f"{page_id} 0 R" for page_id in page_object_ids)
    pages_object = f"<< /Type /Pages /Kids [{kids}] /Count {len(page_object_ids)} >>".encode("ascii")
    catalog_object = b"<< /Type /Catalog /Pages 2 0 R >>"
    font_object = b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(build_pdf_document([catalog_object, pages_object, font_object, *objects]))


def build_standalone_html(payload: dict) -> str:
    primary_route = (payload.get("routes") or [{}])[0]
    next_stop = primary_route.get("next_stop") or {}
    stops = primary_route.get("stops") or []
    summary = payload.get("summary") or {}
    embedded = json.dumps(payload, ensure_ascii=True)

    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Gestor de Rota Empresa</title>
  <style>
    :root {{
      --bg: #f2efe8;
      --panel: rgba(255, 252, 246, 0.92);
      --ink: #16211f;
      --muted: #61706b;
      --accent: #d95d39;
      --green: #2f7a5f;
      --line: rgba(22, 33, 31, 0.08);
      --shadow: 0 24px 60px rgba(26, 38, 34, 0.14);
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: "Avenir Next", "Segoe UI", sans-serif;
      color: var(--ink);
      background:
        radial-gradient(circle at top left, rgba(217, 93, 57, 0.22), transparent 28%),
        radial-gradient(circle at bottom right, rgba(47, 122, 95, 0.18), transparent 24%),
        linear-gradient(145deg, #efe9df 0%, #f8f5ef 44%, #ece6dc 100%);
      min-height: 100vh;
      padding: 24px;
    }}
    .wrap {{
      width: min(1120px, 100%);
      margin: 0 auto;
      display: grid;
      grid-template-columns: 1fr 380px;
      gap: 28px;
      align-items: start;
    }}
    .panel, .hero, .card, .stat {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 28px;
      box-shadow: var(--shadow);
      backdrop-filter: blur(12px);
    }}
    .panel {{ padding: 28px; }}
    h1 {{
      margin: 0 0 12px;
      font-size: clamp(36px, 5vw, 58px);
      line-height: 0.95;
      letter-spacing: -0.04em;
      max-width: 11ch;
    }}
    p {{ color: var(--muted); line-height: 1.6; }}
    .actions, .stats {{ display: flex; flex-wrap: wrap; gap: 12px; }}
    .action {{
      display: inline-flex;
      align-items: center;
      justify-content: center;
      padding: 12px 16px;
      border-radius: 999px;
      background: #fffaf0;
      border: 1px solid var(--line);
      color: var(--ink);
      text-decoration: none;
      font-size: 14px;
      font-weight: 700;
    }}
    .action.secondary {{
      background: #dcefe4;
      color: #1f5d49;
    }}
    .stats {{ margin-top: 22px; }}
    .stat {{ min-width: 160px; padding: 18px; }}
    .stat strong {{ display: block; font-size: 28px; margin-bottom: 6px; }}
    .phone {{
      background: linear-gradient(180deg, #1b2725 0%, #0d1413 100%);
      border-radius: 40px;
      padding: 14px;
    }}
    .screen {{
      background: linear-gradient(180deg, rgba(255, 251, 244, 0.97), rgba(247, 243, 236, 0.96));
      border-radius: 30px;
      padding: 18px;
      min-height: 720px;
    }}
    .hero {{ padding: 18px; margin-bottom: 14px; }}
    .label {{
      display: inline-block;
      padding: 8px 12px;
      border-radius: 999px;
      background: #f6d7bf;
      color: var(--accent);
      font-size: 12px;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.08em;
    }}
    .hero h2 {{ margin: 12px 0 8px; font-size: 28px; line-height: 1.04; }}
    .meta {{
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 10px;
    }}
    .meta .card, .route-card, .status {{
      padding: 12px;
      border-radius: 22px;
      background: #fffaf0;
      border: 1px solid var(--line);
    }}
    .meta strong, .route-card strong {{ display: block; font-size: 15px; }}
    .meta span, .route-card span {{ color: var(--muted); font-size: 13px; }}
    .route-list {{ display: grid; gap: 10px; margin-top: 14px; }}
    .route-card {{ display: flex; gap: 12px; align-items: center; }}
    .route-card-actions {{
      display: flex;
      flex-direction: column;
      gap: 6px;
      align-items: flex-end;
    }}
    .route-index {{
      width: 42px; height: 42px; border-radius: 16px; display: grid; place-items: center;
      background: rgba(22, 33, 31, 0.06); font-weight: 800;
    }}
    .route-copy {{ flex: 1; }}
    .eta {{ color: var(--green); font-size: 13px; font-weight: 700; }}
    .route-link {{
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-width: 78px;
      padding: 8px 10px;
      border-radius: 14px;
      border: 1px solid var(--line);
      background: #ffffff;
      color: var(--ink);
      text-decoration: none;
      font-size: 12px;
      font-weight: 700;
    }}
    .status {{
      margin-top: 14px;
      display: flex;
      justify-content: space-between;
      align-items: center;
    }}
    .tag {{
      background: #dcefe4;
      color: var(--green);
      padding: 8px 12px;
      border-radius: 999px;
      font-size: 12px;
      font-weight: 700;
    }}
    @media (max-width: 980px) {{
      .wrap {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>
  <main class="wrap">
    <section class="panel">
      <div class="label">Link Local Pronto</div>
      <h1>Gestor de rota para uso imediato.</h1>
      <p>Esta versao funciona direto pelo arquivo HTML, sem depender de servidor local. Ela mostra cliente, equipamento, endereco e a sequencia da rota mais recente exportada.</p>
      <div class="actions">
        <a class="action" href="./route-plan.pdf" target="_blank" rel="noreferrer">Baixar PDF</a>
        <a class="action" href="./route-plan-mobile.json" target="_blank" rel="noreferrer">Abrir JSON</a>
        <a class="action secondary" href="{next_stop.get("google_maps_directions_url") or '#'}" target="_blank" rel="noreferrer">Google Maps</a>
      </div>
      <div class="stats">
        <div class="stat">
          <strong>{summary.get("total_deliveries", 0)}</strong>
          <span>paradas planejadas</span>
        </div>
        <div class="stat">
          <strong>{round(float(summary.get("assigned_ratio", 0)) * 100)}%</strong>
          <span>roteirizacao concluida</span>
        </div>
        <div class="stat">
          <strong>{summary.get("total_distance_km", 0)} km</strong>
          <span>distancia total</span>
        </div>
      </div>
    </section>
    <section class="phone">
      <div class="screen">
        <article class="hero">
          <div class="label">Proxima parada</div>
          <h2>{next_stop.get("customer_name") or "Sem cliente"}</h2>
          <p>{next_stop.get("client_type") or "avulso"} • {next_stop.get("equipment_quantity") or 1}x {next_stop.get("equipment_type") or "Equipamento"} • Equip {next_stop.get("equipment_number") or "-"} • {next_stop.get("address") or "Sem endereco"}</p>
          <div class="meta">
            <div class="card">
              <strong>{next_stop.get("arrival") or "--:--"}</strong>
              <span>chegada prevista</span>
            </div>
            <div class="card">
              <strong>{len(stops)}/{summary.get("total_deliveries", 0)}</strong>
              <span>paradas na rota</span>
            </div>
            <div class="card">
              <strong>{primary_route.get("vehicle_id") or "--"}</strong>
              <span>veiculo atual</span>
            </div>
          </div>
        </article>
        <div class="route-list" id="route-list"></div>
        <div class="status">
          <div>
            <strong>Sincronizacao</strong>
            <span style="display:block;color:var(--muted);font-size:13px;">rota embutida no HTML</span>
          </div>
          <div class="tag">Pronto</div>
        </div>
      </div>
    </section>
  </main>
  <script>
    const routeData = {embedded};
    const routeList = document.getElementById("route-list");
    (routeData.routes?.[0]?.stops || []).forEach((stop, index) => {{
      const card = document.createElement("article");
      card.className = "route-card";
      card.innerHTML = `
        <div class="route-index">${{index + 1}}</div>
        <div class="route-copy">
          <strong>${{stop.customer_name || "Sem cliente"}}</strong>
          <span>${{stop.client_type || "avulso"}} • ${{stop.equipment_quantity || 1}}x ${{stop.equipment_type || "Equipamento"}} • Equip ${{stop.equipment_number || "-"}}</span>
        </div>
        <div class="route-card-actions">
          <div class="eta">${{stop.arrival || "--:--"}}</div>
          <a class="route-link" href="${{stop.google_maps_directions_url || '#'}}" target="_blank" rel="noreferrer">Navegar</a>
        </div>
      `;
      routeList.appendChild(card);
    }});
    if (!routeList.children.length) {{
      const card = document.createElement("article");
      card.className = "route-card";
      card.innerHTML = '<div class="route-copy"><strong>Nenhuma parada</strong><span>Gere a rota para atualizar esta tela.</span></div>';
      routeList.appendChild(card);
    }}
  </script>
</body>
</html>
"""


def write_standalone_html(payload: dict, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(build_standalone_html(payload), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate route plan from deliveries and fleet CSV files.")
    parser.add_argument("--deliveries", required=True, type=Path, help="Path to deliveries.csv")
    parser.add_argument("--vehicles", required=True, type=Path, help="Path to vehicles.csv")
    parser.add_argument("--output", required=True, type=Path, help="Output JSON path")
    parser.add_argument("--pdf-output", type=Path, help="Optional PDF route summary output path")
    parser.add_argument("--html-output", type=Path, help="Optional standalone HTML route output path")
    parser.add_argument("--speed-kmph", type=float, default=35.0, help="Average urban speed (km/h)")
    parser.add_argument(
        "--mobile-output",
        "--mobile",
        dest="mobile_output",
        action="store_true",
        help="Write compact mobile-focused JSON with next stop and reduced fields.",
    )
    args = parser.parse_args()

    deliveries = load_deliveries(args.deliveries)
    vehicles = load_vehicles(args.vehicles)
    routes, unassigned = build_routes(deliveries, vehicles, args.speed_kmph)
    payload = serialize(routes, unassigned, vehicles)
    if args.mobile_output:
        payload = serialize_mobile(payload)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    if args.pdf_output:
        write_simple_pdf(build_pdf_lines(payload), args.pdf_output)
    if args.html_output:
        write_standalone_html(payload, args.html_output)
    print(f"Route plan written to: {args.output}")
    if args.pdf_output:
        print(f"PDF written to: {args.pdf_output}")
    if args.html_output:
        print(f"HTML written to: {args.html_output}")
    print(json.dumps(payload["summary"], indent=2))


if __name__ == "__main__":
    main()
