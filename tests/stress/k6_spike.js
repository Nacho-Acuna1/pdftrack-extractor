// ==============================================================================
// PDFtrack - Grafana k6 Spike Test (Modelo Cerrado de Carga)
// ==============================================================================
// Prueba de estrés de alta concurrencia con rampa agresiva para evaluar el
// comportamiento del reverse proxy Traefik v3, la cola de extracción y el
// mecanismo de backpressure HTTP 429/503.
//
// Perfil de carga:
//   - 0 -> 100 VUs en 10s (rampa subida)
//   - 100 VUs sostenidos por 20s (meseta de máxima saturación)
//   - 100 -> 0 VUs en 10s (rampa bajada y drenado)
//   - Duración total: 40 segundos
// ==============================================================================

import http from "k6/http";
import { check } from "k6";
import { Counter, Rate } from "k6/metrics";

// --- Variables de configuración desde entorno k6 ---
const targetUrlRaw = __ENV.TARGET_URL || "http://proxy/extract";
const targetUrl = targetUrlRaw.endsWith("/extract")
  ? targetUrlRaw
  : `${targetUrlRaw.replace(/\/$/, "")}/extract`;

const pdfDir = (__ENV.PDF_DIR || "/tests/stress/pdfs").replace(/\/$/, "");

// 4 PDFs oficiales de la cátedra
const pdfFileNames = [
  "scrum_manager_historias_usuario.pdf",
  "Filosofia Lean.pdf",
  "Essential-Kanban-Condensed-Spanish.pdf",
  "Guide-Spanish-LatinSouth-American.pdf",
];

// Carga en memoria binaria de los 4 PDFs oficiales en contexto init
function loadPdfs(baseDir) {
  return pdfFileNames.map((fileName) => {
    const fullPath = `${baseDir}/${fileName}`;
    return {
      name: fileName,
      data: open(fullPath, "b"),
    };
  });
}

const candidateDirs = [
  __ENV.PDF_DIR,
  "/tests/stress/pdfs",
  "./tests/stress/pdfs",
  "./pdfs",
  "/workspace/tests/stress/pdfs",
].filter(Boolean);

let pdfs = null;
let lastError = null;

for (const dir of candidateDirs) {
  try {
    pdfs = loadPdfs(dir.replace(/\/$/, ""));
    if (pdfs && pdfs.length === 4) {
      break;
    }
  } catch (err) {
    lastError = err;
  }
}

if (!pdfs) {
  throw new Error(
    `No se pudieron cargar los 4 PDFs requeridos: ${lastError ? lastError.message : "Error desconocido"}`
  );
}

// Métricas obligatorias: 3 categorías de respuesta
const exitosas = new Counter("exitosas");
const rechazosControlados = new Counter("rechazos_controlados");
const fallosInesperados = new Counter("fallos_inesperados");

const tasaExitosas = new Rate("tasa_exitosas");
const tasaRechazos = new Rate("tasa_rechazos_controlados");
const tasaFallos = new Rate("tasa_fallos_inesperados");

// Informar a k6 que 200, 429 y 503 son respuestas de protocolo esperadas
http.setResponseCallback(http.expectedStatuses(200, 429, 503));

export const options = {
  scenarios: {
    spike_test: {
      executor: "ramping-vus",
      startVUs: 0,
      stages: [
        { duration: "10s", target: 100 }, // Rampa subida
        { duration: "20s", target: 100 }, // Meseta sostenida
        { duration: "10s", target: 0 },   // Rampa bajada
      ],
      gracefulRampDown: "0s",
    },
  },
  thresholds: {
    // Thresholds obligatorios del TP
    fallos_inesperados: ["count==0"],
    http_req_duration: ["p(95)<30000"],
  },
};

export default function () {
  // Rotación cíclica determinista entre los 4 PDFs por VU e iteración
  const pdf = pdfs[(__VU + __ITER) % pdfs.length];

  const payload = {
    file: http.file(pdf.data, pdf.name, "application/pdf"),
  };

  const params = {
    timeout: "30s",
    tags: { pdf_name: pdf.name },
  };

  const response = http.post(targetUrl, payload, params);

  const isSuccess = response.status === 200;
  const isControlled = response.status === 429 || response.status === 503;
  const isUnexpected = !isSuccess && !isControlled;

  if (isSuccess) {
    exitosas.add(1);
    tasaExitosas.add(1);
    tasaRechazos.add(0);
    tasaFallos.add(0);
  } else if (isControlled) {
    rechazosControlados.add(1);
    tasaExitosas.add(0);
    tasaRechazos.add(1);
    tasaFallos.add(0);
  } else {
    fallosInesperados.add(1);
    tasaExitosas.add(0);
    tasaRechazos.add(0);
    tasaFallos.add(1);
  }

  check(response, {
    "código HTTP controlado (200, 429 o 503)": () => !isUnexpected,
    "contrato JSON válido en 200": (res) => {
      if (!isSuccess) return true;
      try {
        const body = res.json();
        return (
          typeof body.content === "string" &&
          Number.isInteger(body.page_count)
        );
      } catch (_) {
        return false;
      }
    },
  });
}

// Formateador final y exportación obligatoria de k6-summary.json
export function handleSummary(data) {
  const countExitosas = data.metrics.exitosas
    ? data.metrics.exitosas.values.count
    : 0;
  const countRechazos = data.metrics.rechazos_controlados
    ? data.metrics.rechazos_controlados.values.count
    : 0;
  const countFallos = data.metrics.fallos_inesperados
    ? data.metrics.fallos_inesperados.values.count
    : 0;

  const totalReqs = data.metrics.http_reqs
    ? data.metrics.http_reqs.values.count
    : 0;
  const rateReqs = data.metrics.http_reqs
    ? data.metrics.http_reqs.values.rate.toFixed(2)
    : "0.00";

  const p50Duration =
    data.metrics.http_req_duration &&
    data.metrics.http_req_duration.values["med"] !== undefined
      ? (data.metrics.http_req_duration.values["med"] / 1000).toFixed(2)
      : (data.metrics.http_req_duration && data.metrics.http_req_duration.values["p(50)"] !== undefined
        ? (data.metrics.http_req_duration.values["p(50)"] / 1000).toFixed(2)
        : "0.00");

  const p90Duration =
    data.metrics.http_req_duration &&
    data.metrics.http_req_duration.values["p(90)"] !== undefined
      ? (data.metrics.http_req_duration.values["p(90)"] / 1000).toFixed(2)
      : "0.00";

  const p95Duration =
    data.metrics.http_req_duration &&
    data.metrics.http_req_duration.values["p(95)"] !== undefined
      ? (data.metrics.http_req_duration.values["p(95)"] / 1000).toFixed(2)
      : "0.00";

  const maxDuration =
    data.metrics.http_req_duration &&
    data.metrics.http_req_duration.values["max"] !== undefined
      ? (data.metrics.http_req_duration.values["max"] / 1000).toFixed(2)
      : "0.00";

  const meetsThresholds = countFallos === 0 && parseFloat(p95Duration) < 30;

  const summaryText = `
================================================================================
 PDFtrack - Resumen de Prueba de Estrés Grafana k6 (Spike Test)
================================================================================
 Categoría                        | Cantidad   | Porcentaje | Referencia
--------------------------------------------------------------------------------
 Solicitudes Exitosas (HTTP 200)  | ${String(countExitosas).padEnd(10)} | ${(
    (countExitosas / (totalReqs || 1)) *
    100
  ).toFixed(2)}%    | Procesadas
 Rechazos Controlados (429 / 503) | ${String(countRechazos).padEnd(10)} | ${(
    (countRechazos / (totalReqs || 1)) *
    100
  ).toFixed(2)}%    | Backpressure esperado
 Fallos Inesperados (otros)       | ${String(countFallos).padEnd(10)} | ${(
    (countFallos / (totalReqs || 1)) *
    100
  ).toFixed(2)}%    | 0 (Obligatorio)
--------------------------------------------------------------------------------
 Total Peticiones Generadas:      ${totalReqs}
 Throughput Global:               ${rateReqs} req/s (Referencia cátedra: > 25.35 req/s)
 Latencia p(50):                  ${p50Duration} s
 Latencia p(90):                  ${p90Duration} s
 Latencia p(95):                  ${p95Duration} s   (Referencia cátedra: < 30.00 s)
 Latencia Máxima:                 ${maxDuration} s
--------------------------------------------------------------------------------
 Resultado del Test: ${
   meetsThresholds
     ? "EXITOSO / APROBADO (Sin fallos inesperados, latencia bajo umbral)"
     : "FALLIDO (Incumple thresholds obligatorios)"
 }
================================================================================
`;

  return {
    stdout: summaryText,
    "/tests/stress/results/k6-report.json": JSON.stringify(data, null, 2),
  };
}
