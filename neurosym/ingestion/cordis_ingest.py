"""CORDIS Horizon Europe data ingestion into DuckDB with schema extraction using PyArrow."""

import csv
import io
import json
import logging
import os
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import duckdb
import pyarrow as pa

from neurosym.schema.master_schema import (
    DucklingDimension,
    EntitySchema,
    JoinPath,
    MasterSchema,
    ParameterSchema,
    SemanticType,
)

logger = logging.getLogger(__name__)

DEFAULT_DATA_DIR = Path("CORDIS - EU research projects under HORIZON EUROPE (2021-2027)/Publications Office")
DEFAULT_DB_PATH = Path("cordis.duckdb")
DEFAULT_SCHEMA_PATH = Path("master_schema.json")

COUNTRY_MAP = {
    "DE": "Germany", "FR": "France", "IT": "Italy", "ES": "Spain",
    "NL": "Netherlands", "BE": "Belgium", "AT": "Austria", "PL": "Poland",
    "SE": "Sweden", "DK": "Denmark", "FI": "Finland", "NO": "Norway",
    "CH": "Switzerland", "UK": "United Kingdom", "GB": "United Kingdom",
    "IE": "Ireland", "PT": "Portugal", "GR": "Greece", "EL": "Greece",
    "CZ": "Czech Republic", "HU": "Hungary", "RO": "Romania", "BG": "Bulgaria",
    "HR": "Croatia", "SK": "Slovakia", "SI": "Slovenia", "EE": "Estonia",
    "LV": "Latvia", "LT": "Lithuania", "CY": "Cyprus", "MT": "Malta",
    "LU": "Luxembourg", "IS": "Iceland", "IL": "Israel", "TR": "Turkey",
    "UA": "Ukraine", "RS": "Serbia", "US": "United States", "CA": "Canada",
    "JP": "Japan", "AU": "Australia", "CN": "China", "IN": "India",
    "BR": "Brazil", "KR": "South Korea", "ZA": "South Africa"
}


def _parse_float(val: Optional[str]) -> Optional[float]:
    if not val:
        return None
    val = val.strip().replace(",", ".")
    if not val:
        return None
    try:
        return float(val)
    except ValueError:
        return None


def _parse_int(val: Optional[str]) -> Optional[int]:
    if not val:
        return None
    val = val.strip()
    if not val:
        return None
    try:
        return int(float(val))
    except ValueError:
        return None


def _parse_date(val: Optional[str]) -> Optional[str]:
    if not val:
        return None
    val = val.strip()
    if len(val) == 10 and val[4] == "-" and val[7] == "-":
        return val
    return None


def _parse_bool(val: Optional[str]) -> bool:
    if not val:
        return False
    val = val.strip().lower()
    return val in ("true", "1", "yes", "y")


class CordisIngestionEngine:
    """Extracts, cleans, and loads CORDIS data into DuckDB and generates the Master Schema."""

    def __init__(self, data_dir: Path = DEFAULT_DATA_DIR, db_path: Path = DEFAULT_DB_PATH):
        self.data_dir = Path(data_dir)
        self.db_path = Path(db_path)

    def ingest_all(self) -> MasterSchema:
        """Runs the entire ingestion pipeline and returns the MasterSchema."""
        print(f"Starting CORDIS ingestion into {self.db_path}...")
        
        # Connect to DuckDB
        con = duckdb.connect(str(self.db_path))
        try:
            # 1. Projects and related tables
            self._ingest_projects_zip(con)

            # 2. Deliverables
            self._ingest_deliverables_zip(con)

            # 3. Publications
            self._ingest_publications_zip(con)

            # 4. Reports
            self._ingest_reports_zip(con)

            # 5. Create Enriched Views
            self._create_indices_and_views(con)

            # 6. Extract Master Schema
            master_schema = self._build_master_schema(con)

            # Save schema JSON
            with open(DEFAULT_SCHEMA_PATH, "w", encoding="utf-8") as f:
                f.write(master_schema.model_dump_json(indent=2))

            print(f"Ingestion completed successfully. Master Schema saved to {DEFAULT_SCHEMA_PATH}.")
            return master_schema
        finally:
            con.close()

    def _ingest_projects_zip(self, con: duckdb.DuckDBPyConnection):
        zip_path = self.data_dir / "8-cordis-HORIZONprojects-csv.zip"
        if not zip_path.exists():
            return

        with zipfile.ZipFile(zip_path) as zf:
            # 1. project
            if "project.csv" in zf.namelist():
                print("Ingesting project.csv...")
                with zf.open("project.csv") as f:
                    reader = csv.reader(io.TextIOWrapper(f, encoding="utf-8", errors="replace"), delimiter=";")
                    next(reader, None)
                    cols = {
                        "id": [], "acronym": [], "status": [], "title": [],
                        "startDate": [], "endDate": [], "totalCost": [], "ecMaxContribution": [],
                        "topics": [], "ecSignatureDate": [], "frameworkProgramme": [],
                        "masterCall": [], "subCall": [], "fundingScheme": [], "nature": [],
                        "objective": [], "rcn": [], "grantDoi": [], "keywords": [], "legalBasis": []
                    }
                    for r in reader:
                        if len(r) >= 22 and r[0].strip():
                            cols["id"].append(r[0].strip())
                            cols["acronym"].append(r[1].strip())
                            cols["status"].append(r[2].strip())
                            cols["title"].append(r[3].strip())
                            cols["startDate"].append(_parse_date(r[4]))
                            cols["endDate"].append(_parse_date(r[5]))
                            cols["totalCost"].append(_parse_float(r[6]))
                            cols["ecMaxContribution"].append(_parse_float(r[7]))
                            cols["topics"].append(r[8].strip())
                            cols["ecSignatureDate"].append(_parse_date(r[9]))
                            cols["frameworkProgramme"].append(r[10].strip())
                            cols["masterCall"].append(r[11].strip())
                            cols["subCall"].append(r[12].strip())
                            cols["fundingScheme"].append(r[13].strip())
                            cols["nature"].append(r[14].strip())
                            cols["objective"].append(r[15].strip())
                            cols["rcn"].append(r[17].strip())
                            cols["grantDoi"].append(r[18].strip())
                            cols["keywords"].append(r[19].strip())
                            cols["legalBasis"].append(r[21].strip())

                    pa_tbl = pa.Table.from_pydict({
                        "id": pa.array(cols["id"], type=pa.string()),
                        "acronym": pa.array(cols["acronym"], type=pa.string()),
                        "status": pa.array(cols["status"], type=pa.string()),
                        "title": pa.array(cols["title"], type=pa.string()),
                        "startDate": pa.array(cols["startDate"], type=pa.string()),
                        "endDate": pa.array(cols["endDate"], type=pa.string()),
                        "totalCost": pa.array(cols["totalCost"], type=pa.float64()),
                        "ecMaxContribution": pa.array(cols["ecMaxContribution"], type=pa.float64()),
                        "topics": pa.array(cols["topics"], type=pa.string()),
                        "ecSignatureDate": pa.array(cols["ecSignatureDate"], type=pa.string()),
                        "frameworkProgramme": pa.array(cols["frameworkProgramme"], type=pa.string()),
                        "masterCall": pa.array(cols["masterCall"], type=pa.string()),
                        "subCall": pa.array(cols["subCall"], type=pa.string()),
                        "fundingScheme": pa.array(cols["fundingScheme"], type=pa.string()),
                        "nature": pa.array(cols["nature"], type=pa.string()),
                        "objective": pa.array(cols["objective"], type=pa.string()),
                        "rcn": pa.array(cols["rcn"], type=pa.string()),
                        "grantDoi": pa.array(cols["grantDoi"], type=pa.string()),
                        "keywords": pa.array(cols["keywords"], type=pa.string()),
                        "legalBasis": pa.array(cols["legalBasis"], type=pa.string()),
                    })
                    con.register("_pa_project", pa_tbl)
                    con.execute("""
                    CREATE OR REPLACE TABLE project AS 
                    SELECT 
                        id, acronym, status, title,
                        TRY_CAST(startDate AS DATE) AS startDate,
                        TRY_CAST(endDate AS DATE) AS endDate,
                        totalCost, ecMaxContribution, topics,
                        TRY_CAST(ecSignatureDate AS DATE) AS ecSignatureDate,
                        frameworkProgramme, masterCall, subCall, fundingScheme, nature, objective,
                        rcn, grantDoi, keywords, legalBasis
                    FROM _pa_project
                    """)
                    con.unregister("_pa_project")
                count = con.execute("SELECT COUNT(*) FROM project").fetchone()[0]
                print(f"Loaded project: {count:,} rows")

            # 2. organization
            if "organization.csv" in zf.namelist():
                print("Ingesting organization.csv...")
                with zf.open("organization.csv") as f:
                    reader = csv.reader(io.TextIOWrapper(f, encoding="utf-8", errors="replace"), delimiter=";")
                    next(reader, None)
                    cols = {
                        "projectID": [], "projectAcronym": [], "organisationID": [], "vatNumber": [],
                        "name": [], "shortName": [], "SME": [], "activityType": [], "street": [],
                        "postCode": [], "city": [], "country": [], "nutsCode": [], "organizationURL": [],
                        "contactForm": [], "role": [], "ecContribution": [], "netEcContribution": [],
                        "totalCost": [], "active": []
                    }
                    for r in reader:
                        if len(r) >= 25 and r[0].strip():
                            cols["projectID"].append(r[0].strip())
                            cols["projectAcronym"].append(r[1].strip())
                            cols["organisationID"].append(r[2].strip())
                            cols["vatNumber"].append(r[3].strip())
                            cols["name"].append(r[4].strip())
                            cols["shortName"].append(r[5].strip())
                            cols["SME"].append(_parse_bool(r[6]))
                            cols["activityType"].append(r[7].strip())
                            cols["street"].append(r[8].strip())
                            cols["postCode"].append(r[9].strip())
                            cols["city"].append(r[10].strip())
                            cols["country"].append(r[11].strip().upper())
                            cols["nutsCode"].append(r[12].strip())
                            cols["organizationURL"].append(r[14].strip())
                            cols["contactForm"].append(r[15].strip())
                            cols["role"].append(r[19].strip().lower())
                            cols["ecContribution"].append(_parse_float(r[20]))
                            cols["netEcContribution"].append(_parse_float(r[21]))
                            cols["totalCost"].append(_parse_float(r[22]))
                            cols["active"].append(_parse_bool(r[24]))

                    pa_org = pa.Table.from_pydict({
                        "projectID": pa.array(cols["projectID"], type=pa.string()),
                        "projectAcronym": pa.array(cols["projectAcronym"], type=pa.string()),
                        "organisationID": pa.array(cols["organisationID"], type=pa.string()),
                        "vatNumber": pa.array(cols["vatNumber"], type=pa.string()),
                        "name": pa.array(cols["name"], type=pa.string()),
                        "shortName": pa.array(cols["shortName"], type=pa.string()),
                        "SME": pa.array(cols["SME"], type=pa.bool_()),
                        "activityType": pa.array(cols["activityType"], type=pa.string()),
                        "street": pa.array(cols["street"], type=pa.string()),
                        "postCode": pa.array(cols["postCode"], type=pa.string()),
                        "city": pa.array(cols["city"], type=pa.string()),
                        "country": pa.array(cols["country"], type=pa.string()),
                        "nutsCode": pa.array(cols["nutsCode"], type=pa.string()),
                        "organizationURL": pa.array(cols["organizationURL"], type=pa.string()),
                        "contactForm": pa.array(cols["contactForm"], type=pa.string()),
                        "role": pa.array(cols["role"], type=pa.string()),
                        "ecContribution": pa.array(cols["ecContribution"], type=pa.float64()),
                        "netEcContribution": pa.array(cols["netEcContribution"], type=pa.float64()),
                        "totalCost": pa.array(cols["totalCost"], type=pa.float64()),
                        "active": pa.array(cols["active"], type=pa.bool_()),
                    })
                    con.register("_pa_org", pa_org)
                    con.execute("CREATE OR REPLACE TABLE organization AS SELECT * FROM _pa_org")
                    con.unregister("_pa_org")
                count = con.execute("SELECT COUNT(*) FROM organization").fetchone()[0]
                print(f"Loaded organization: {count:,} rows")

            # 3. euroSciVoc
            if "euroSciVoc.csv" in zf.namelist():
                print("Ingesting euroSciVoc.csv...")
                with zf.open("euroSciVoc.csv") as f:
                    reader = csv.reader(io.TextIOWrapper(f, encoding="utf-8", errors="replace"), delimiter=";")
                    next(reader, None)
                    cols = {
                        "euroSciVocCode": [], "euroSciVocPath": [],
                        "euroSciVocTitle": [], "euroSciVocDescription": [], "projectID": []
                    }
                    for r in reader:
                        if len(r) >= 5 and r[4].strip():
                            cols["euroSciVocCode"].append(r[0].strip())
                            cols["euroSciVocPath"].append(r[1].strip())
                            cols["euroSciVocTitle"].append(r[2].strip())
                            cols["euroSciVocDescription"].append(r[3].strip())
                            cols["projectID"].append(r[4].strip())

                    pa_euro = pa.Table.from_pydict({
                        k: pa.array(v, type=pa.string()) for k, v in cols.items()
                    })
                    con.register("_pa_euro", pa_euro)
                    con.execute("CREATE OR REPLACE TABLE euroSciVoc AS SELECT * FROM _pa_euro")
                    con.unregister("_pa_euro")
                count = con.execute("SELECT COUNT(*) FROM euroSciVoc").fetchone()[0]
                print(f"Loaded euroSciVoc: {count:,} rows")

            # 4. topics
            if "topics.csv" in zf.namelist():
                print("Ingesting topics.csv...")
                with zf.open("topics.csv") as f:
                    reader = csv.reader(io.TextIOWrapper(f, encoding="utf-8", errors="replace"), delimiter=";")
                    next(reader, None)
                    cols = {"topic": [], "title": [], "projectID": []}
                    for r in reader:
                        if len(r) >= 3 and r[2].strip():
                            cols["topic"].append(r[0].strip())
                            cols["title"].append(r[1].strip())
                            cols["projectID"].append(r[2].strip())

                    pa_top = pa.Table.from_pydict({
                        k: pa.array(v, type=pa.string()) for k, v in cols.items()
                    })
                    con.register("_pa_top", pa_top)
                    con.execute("CREATE OR REPLACE TABLE topics AS SELECT * FROM _pa_top")
                    con.unregister("_pa_top")
                count = con.execute("SELECT COUNT(*) FROM topics").fetchone()[0]
                print(f"Loaded topics: {count:,} rows")

            # 5. legalBasis
            if "legalBasis.csv" in zf.namelist():
                print("Ingesting legalBasis.csv...")
                with zf.open("legalBasis.csv") as f:
                    reader = csv.reader(io.TextIOWrapper(f, encoding="utf-8", errors="replace"), delimiter=";")
                    next(reader, None)
                    cols = {"legalBasis": [], "title": [], "uniqueProgrammePart": [], "projectID": []}
                    for r in reader:
                        if len(r) >= 4 and r[3].strip():
                            cols["legalBasis"].append(r[0].strip())
                            cols["title"].append(r[1].strip())
                            cols["uniqueProgrammePart"].append(r[2].strip())
                            cols["projectID"].append(r[3].strip())

                    pa_leg = pa.Table.from_pydict({
                        k: pa.array(v, type=pa.string()) for k, v in cols.items()
                    })
                    con.register("_pa_leg", pa_leg)
                    con.execute("CREATE OR REPLACE TABLE legalBasis AS SELECT * FROM _pa_leg")
                    con.unregister("_pa_leg")
                count = con.execute("SELECT COUNT(*) FROM legalBasis").fetchone()[0]
                print(f"Loaded legalBasis: {count:,} rows")

            # 6. policyPriorities
            if "policyPriorities.csv" in zf.namelist():
                print("Ingesting policyPriorities.csv...")
                with zf.open("policyPriorities.csv") as f:
                    reader = csv.reader(io.TextIOWrapper(f, encoding="utf-8", errors="replace"), delimiter=";")
                    next(reader, None)
                    cols = {
                        "projectID": [], "ai": [], "biodiversity": [],
                        "cleanAir": [], "climate": [], "digitalAgenda": []
                    }
                    for r in reader:
                        if len(r) >= 6 and r[5].strip():
                            cols["projectID"].append(r[5].strip())
                            cols["ai"].append(_parse_float(r[0]))
                            cols["biodiversity"].append(_parse_float(r[1]))
                            cols["cleanAir"].append(_parse_float(r[2]))
                            cols["climate"].append(_parse_float(r[3]))
                            cols["digitalAgenda"].append(_parse_float(r[4]))

                    pa_pol = pa.Table.from_pydict({
                        "projectID": pa.array(cols["projectID"], type=pa.string()),
                        "ai": pa.array(cols["ai"], type=pa.float64()),
                        "biodiversity": pa.array(cols["biodiversity"], type=pa.float64()),
                        "cleanAir": pa.array(cols["cleanAir"], type=pa.float64()),
                        "climate": pa.array(cols["climate"], type=pa.float64()),
                        "digitalAgenda": pa.array(cols["digitalAgenda"], type=pa.float64()),
                    })
                    con.register("_pa_pol", pa_pol)
                    con.execute("CREATE OR REPLACE TABLE policyPriorities AS SELECT * FROM _pa_pol")
                    con.unregister("_pa_pol")
                count = con.execute("SELECT COUNT(*) FROM policyPriorities").fetchone()[0]
                print(f"Loaded policyPriorities: {count:,} rows")

    def _ingest_deliverables_zip(self, con: duckdb.DuckDBPyConnection):
        zip_path = self.data_dir / "2-cordis-HORIZONprojectDeliverables-csv.zip"
        if not zip_path.exists():
            return

        with zipfile.ZipFile(zip_path) as zf:
            if "projectDeliverables.csv" in zf.namelist():
                print("Ingesting projectDeliverables.csv...")
                with zf.open("projectDeliverables.csv") as f:
                    reader = csv.reader(io.TextIOWrapper(f, encoding="utf-8", errors="replace"), delimiter=";")
                    next(reader, None)
                    cols = {"deliverableType": [], "description": [], "url": [], "projectID": [], "projectAcronym": []}
                    for r in reader:
                        if len(r) >= 5 and r[3].strip():
                            cols["deliverableType"].append(r[0].strip())
                            cols["description"].append(r[1].strip())
                            cols["url"].append(r[2].strip())
                            cols["projectID"].append(r[3].strip())
                            cols["projectAcronym"].append(r[4].strip())

                    pa_del = pa.Table.from_pydict({
                        k: pa.array(v, type=pa.string()) for k, v in cols.items()
                    })
                    con.register("_pa_del", pa_del)
                    con.execute("CREATE OR REPLACE TABLE projectDeliverables AS SELECT * FROM _pa_del")
                    con.unregister("_pa_del")
                count = con.execute("SELECT COUNT(*) FROM projectDeliverables").fetchone()[0]
                print(f"Loaded projectDeliverables: {count:,} rows")

    def _ingest_publications_zip(self, con: duckdb.DuckDBPyConnection):
        zip_path = self.data_dir / "3-cordis-HORIZONprojectPublications-csv.zip"
        if not zip_path.exists():
            return

        with zipfile.ZipFile(zip_path) as zf:
            if "projectPublications.csv" in zf.namelist():
                print("Ingesting projectPublications.csv...")
                with zf.open("projectPublications.csv") as f:
                    reader = csv.reader(io.TextIOWrapper(f, encoding="utf-8", errors="replace"), delimiter=";")
                    next(reader, None)
                    cols = {
                        "id": [], "title": [], "isPublishedAs": [], "authors": [],
                        "journalTitle": [], "publishedYear": [], "publisher": [],
                        "doi": [], "projectID": [], "projectAcronym": []
                    }
                    for r in reader:
                        if len(r) >= 14 and r[12].strip():
                            cols["id"].append(r[0].strip())
                            cols["title"].append(r[1].strip())
                            cols["isPublishedAs"].append(r[2].strip())
                            cols["authors"].append(r[3].strip())
                            cols["journalTitle"].append(r[5].strip())
                            cols["publishedYear"].append(_parse_int(r[7]))
                            cols["publisher"].append(r[8].strip())
                            cols["doi"].append(r[11].strip())
                            cols["projectID"].append(r[12].strip())
                            cols["projectAcronym"].append(r[13].strip())

                    pa_pub = pa.Table.from_pydict({
                        "id": pa.array(cols["id"], type=pa.string()),
                        "title": pa.array(cols["title"], type=pa.string()),
                        "isPublishedAs": pa.array(cols["isPublishedAs"], type=pa.string()),
                        "authors": pa.array(cols["authors"], type=pa.string()),
                        "journalTitle": pa.array(cols["journalTitle"], type=pa.string()),
                        "publishedYear": pa.array(cols["publishedYear"], type=pa.int32()),
                        "publisher": pa.array(cols["publisher"], type=pa.string()),
                        "doi": pa.array(cols["doi"], type=pa.string()),
                        "projectID": pa.array(cols["projectID"], type=pa.string()),
                        "projectAcronym": pa.array(cols["projectAcronym"], type=pa.string()),
                    })
                    con.register("_pa_pub", pa_pub)
                    con.execute("CREATE OR REPLACE TABLE projectPublications AS SELECT * FROM _pa_pub")
                    con.unregister("_pa_pub")
                count = con.execute("SELECT COUNT(*) FROM projectPublications").fetchone()[0]
                print(f"Loaded projectPublications: {count:,} rows")

    def _ingest_reports_zip(self, con: duckdb.DuckDBPyConnection):
        zip_path = self.data_dir / "5-cordis-HORIZONreports-csv.zip"
        if not zip_path.exists():
            return

        with zipfile.ZipFile(zip_path) as zf:
            if "reportSummaries.csv" in zf.namelist():
                print("Ingesting reportSummaries.csv...")
                with zf.open("reportSummaries.csv") as f:
                    reader = csv.reader(io.TextIOWrapper(f, encoding="utf-8", errors="replace"), delimiter=";")
                    next(reader, None)
                    cols = {"id": [], "title": [], "projectID": [], "projectAcronym": []}
                    for r in reader:
                        if len(r) >= 5 and r[3].strip():
                            cols["id"].append(r[1].strip())
                            cols["title"].append(r[2].strip())
                            cols["projectID"].append(r[3].strip())
                            cols["projectAcronym"].append(r[4].strip())

                    pa_rep = pa.Table.from_pydict({
                        k: pa.array(v, type=pa.string()) for k, v in cols.items()
                    })
                    con.register("_pa_rep", pa_rep)
                    con.execute("CREATE OR REPLACE TABLE reportSummaries AS SELECT * FROM _pa_rep")
                    con.unregister("_pa_rep")
                count = con.execute("SELECT COUNT(*) FROM reportSummaries").fetchone()[0]
                print(f"Loaded reportSummaries: {count:,} rows")

    def _create_indices_and_views(self, con: duckdb.DuckDBPyConnection):
        """Creates unified query views in DuckDB."""
        print("Creating analytical views...")
        con.execute("""
        CREATE OR REPLACE VIEW v_project_enriched AS
        SELECT
            p.id,
            p.acronym,
            p.status,
            p.title,
            p.startDate,
            p.endDate,
            p.totalCost,
            p.ecMaxContribution,
            p.fundingScheme,
            p.frameworkProgramme,
            p.keywords,
            p.objective,
            p.legalBasis,
            COUNT(DISTINCT o.organisationID) AS num_organizations,
            STRING_AGG(DISTINCT o.country, ', ') AS participant_countries,
            MAX(CASE WHEN o.role = 'coordinator' THEN o.name ELSE NULL END) AS coordinator_name,
            MAX(CASE WHEN o.role = 'coordinator' THEN o.country ELSE NULL END) AS coordinator_country,
            STRING_AGG(DISTINCT e.euroSciVocTitle, ' | ') AS scientific_topics
        FROM project p
        LEFT JOIN organization o ON p.id = o.projectID
        LEFT JOIN euroSciVoc e ON p.id = e.projectID
        GROUP BY p.id, p.acronym, p.status, p.title, p.startDate, p.endDate, 
                 p.totalCost, p.ecMaxContribution, p.fundingScheme, 
                 p.frameworkProgramme, p.keywords, p.objective, p.legalBasis
        """)

    def _build_master_schema(self, con: duckdb.DuckDBPyConnection) -> MasterSchema:
        """Builds the comprehensive MasterSchema object with vocabularies and field metadata."""
        print("Extracting Master Schema parameters & vocabularies...")

        schema = MasterSchema(
            version="1.0.0",
            generated_at=datetime.utcnow().isoformat(),
            database_file=str(self.db_path)
        )

        # Entity 1: project
        project_params = {
            "id": ParameterSchema(
                name="id", table="project", column="id", sql_type="VARCHAR",
                semantic_type=SemanticType.KEYWORD, description="Unique CORDIS project grant identifier."
            ),
            "acronym": ParameterSchema(
                name="acronym", table="project", column="acronym", sql_type="VARCHAR",
                semantic_type=SemanticType.KEYWORD, description="Project short name or acronym."
            ),
            "title": ParameterSchema(
                name="title", table="project", column="title", sql_type="VARCHAR",
                semantic_type=SemanticType.TEXT, description="Full title of the research project."
            ),
            "status": ParameterSchema(
                name="status", table="project", column="status", sql_type="VARCHAR",
                semantic_type=SemanticType.KEYWORD, description="Project status (SIGNED, CLOSED, TERMINATED)."
            ),
            "startDate": ParameterSchema(
                name="startDate", table="project", column="startDate", sql_type="DATE",
                semantic_type=SemanticType.DATE, duckling_dimension=DucklingDimension.TIME,
                description="Project start date (YYYY-MM-DD)."
            ),
            "endDate": ParameterSchema(
                name="endDate", table="project", column="endDate", sql_type="DATE",
                semantic_type=SemanticType.DATE, duckling_dimension=DucklingDimension.TIME,
                description="Project end date (YYYY-MM-DD)."
            ),
            "totalCost": ParameterSchema(
                name="totalCost", table="project", column="totalCost", sql_type="DOUBLE",
                semantic_type=SemanticType.AMOUNT_OF_MONEY, duckling_dimension=DucklingDimension.AMOUNT_OF_MONEY,
                unit="EUR", description="Total project budget in Euros."
            ),
            "ecMaxContribution": ParameterSchema(
                name="ecMaxContribution", table="project", column="ecMaxContribution", sql_type="DOUBLE",
                semantic_type=SemanticType.AMOUNT_OF_MONEY, duckling_dimension=DucklingDimension.AMOUNT_OF_MONEY,
                unit="EUR", description="Maximum financial contribution awarded by the European Commission in Euros."
            ),
            "fundingScheme": ParameterSchema(
                name="fundingScheme", table="project", column="fundingScheme", sql_type="VARCHAR",
                semantic_type=SemanticType.KEYWORD, description="Funding scheme (HORIZON-RIA, HORIZON-IA, HORIZON-CSA, HORIZON-ERC, etc.)."
            ),
            "nature": ParameterSchema(
                name="nature", table="project", column="nature", sql_type="VARCHAR",
                semantic_type=SemanticType.KEYWORD, description="Nature of the action."
            ),
            "objective": ParameterSchema(
                name="objective", table="project", column="objective", sql_type="VARCHAR",
                semantic_type=SemanticType.TEXT, description="Abstract and scientific objectives."
            ),
            "keywords": ParameterSchema(
                name="keywords", table="project", column="keywords", sql_type="VARCHAR",
                semantic_type=SemanticType.TEXT, description="Domain keywords."
            ),
            "legalBasis": ParameterSchema(
                name="legalBasis", table="project", column="legalBasis", sql_type="VARCHAR",
                semantic_type=SemanticType.KEYWORD, description="Pillar / legal basis code."
            ),
        }

        stats = con.execute("""
        SELECT 
            MIN(startDate), MAX(startDate),
            MIN(endDate), MAX(endDate),
            MIN(totalCost), MAX(totalCost),
            MIN(ecMaxContribution), MAX(ecMaxContribution),
            COUNT(*)
        FROM project
        """).fetchone()

        if stats:
            project_params["startDate"].min_value = str(stats[0])
            project_params["startDate"].max_value = str(stats[1])
            project_params["endDate"].min_value = str(stats[2])
            project_params["endDate"].max_value = str(stats[3])
            project_params["totalCost"].min_value = stats[4]
            project_params["totalCost"].max_value = stats[5]
            project_params["ecMaxContribution"].min_value = stats[6]
            project_params["ecMaxContribution"].max_value = stats[7]
            row_count = stats[8]
        else:
            row_count = 0

        schema.entities["project"] = EntitySchema(
            name="project",
            table_name="project",
            description="EU Horizon Europe research projects, metadata, budgets, and timelines.",
            primary_key="id",
            parameters=project_params,
            row_count=row_count
        )

        # Entity 2: organization
        org_params = {
            "projectID": ParameterSchema(
                name="projectID", table="organization", column="projectID", sql_type="VARCHAR",
                semantic_type=SemanticType.KEYWORD, description="Reference to project ID."
            ),
            "organisationID": ParameterSchema(
                name="organisationID", table="organization", column="organisationID", sql_type="VARCHAR",
                semantic_type=SemanticType.KEYWORD, description="Unique organisation PIC identifier."
            ),
            "name": ParameterSchema(
                name="name", table="organization", column="name", sql_type="VARCHAR",
                semantic_type=SemanticType.TEXT, description="Legal name of organization."
            ),
            "shortName": ParameterSchema(
                name="shortName", table="organization", column="shortName", sql_type="VARCHAR",
                semantic_type=SemanticType.KEYWORD, description="Short name of organization."
            ),
            "SME": ParameterSchema(
                name="SME", table="organization", column="SME", sql_type="BOOLEAN",
                semantic_type=SemanticType.BOOLEAN, description="Whether organization is an SME."
            ),
            "activityType": ParameterSchema(
                name="activityType", table="organization", column="activityType", sql_type="VARCHAR",
                semantic_type=SemanticType.KEYWORD, description="Organization classification."
            ),
            "city": ParameterSchema(
                name="city", table="organization", column="city", sql_type="VARCHAR",
                semantic_type=SemanticType.KEYWORD, description="City."
            ),
            "country": ParameterSchema(
                name="country", table="organization", column="country", sql_type="VARCHAR",
                semantic_type=SemanticType.COUNTRY_CODE, description="ISO 2-letter country code."
            ),
            "role": ParameterSchema(
                name="role", table="organization", column="role", sql_type="VARCHAR",
                semantic_type=SemanticType.KEYWORD, description="Role: coordinator, participant, partner."
            ),
            "ecContribution": ParameterSchema(
                name="ecContribution", table="organization", column="ecContribution", sql_type="DOUBLE",
                semantic_type=SemanticType.AMOUNT_OF_MONEY, duckling_dimension=DucklingDimension.AMOUNT_OF_MONEY,
                unit="EUR", description="EC funding allocated to this organization."
            ),
        }
        org_count = con.execute("SELECT COUNT(*) FROM organization").fetchone()[0]
        schema.entities["organization"] = EntitySchema(
            name="organization",
            table_name="organization",
            description="Participating organizations, universities, SMEs, institutes, and coordinators in Horizon projects.",
            primary_key="organisationID",
            foreign_keys={"projectID": "project.id"},
            parameters=org_params,
            row_count=org_count
        )

        # Entity 3: euroSciVoc
        euro_params = {
            "euroSciVocCode": ParameterSchema(
                name="euroSciVocCode", table="euroSciVoc", column="euroSciVocCode", sql_type="VARCHAR",
                semantic_type=SemanticType.KEYWORD, description="EuroSciVoc classification code."
            ),
            "euroSciVocPath": ParameterSchema(
                name="euroSciVocPath", table="euroSciVoc", column="euroSciVocPath", sql_type="VARCHAR",
                semantic_type=SemanticType.TEXT, description="Taxonomy hierarchy path."
            ),
            "euroSciVocTitle": ParameterSchema(
                name="euroSciVocTitle", table="euroSciVoc", column="euroSciVocTitle", sql_type="VARCHAR",
                semantic_type=SemanticType.KEYWORD, description="Scientific subfield title."
            ),
            "projectID": ParameterSchema(
                name="projectID", table="euroSciVoc", column="projectID", sql_type="VARCHAR",
                semantic_type=SemanticType.KEYWORD, description="Associated project ID."
            ),
        }
        euro_count = con.execute("SELECT COUNT(*) FROM euroSciVoc").fetchone()[0]
        schema.entities["euroSciVoc"] = EntitySchema(
            name="euroSciVoc",
            table_name="euroSciVoc",
            description="European Science Vocabulary (EuroSciVoc) taxonomy classifications mapped to projects.",
            foreign_keys={"projectID": "project.id"},
            parameters=euro_params,
            row_count=euro_count
        )

        # Entity 4: projectDeliverables
        deliv_params = {
            "deliverableType": ParameterSchema(
                name="deliverableType", table="projectDeliverables", column="deliverableType", sql_type="VARCHAR",
                semantic_type=SemanticType.KEYWORD, description="Type of deliverable."
            ),
            "description": ParameterSchema(
                name="description", table="projectDeliverables", column="description", sql_type="VARCHAR",
                semantic_type=SemanticType.TEXT, description="Deliverable title and description."
            ),
            "url": ParameterSchema(
                name="url", table="projectDeliverables", column="url", sql_type="VARCHAR",
                semantic_type=SemanticType.URL, description="Reference URL."
            ),
            "projectID": ParameterSchema(
                name="projectID", table="projectDeliverables", column="projectID", sql_type="VARCHAR",
                semantic_type=SemanticType.KEYWORD, description="Associated project ID."
            ),
        }
        deliv_count = con.execute("SELECT COUNT(*) FROM projectDeliverables").fetchone()[0]
        schema.entities["projectDeliverables"] = EntitySchema(
            name="projectDeliverables",
            table_name="projectDeliverables",
            description="Project deliverables, prototypes, reports, and websites.",
            foreign_keys={"projectID": "project.id"},
            parameters=deliv_params,
            row_count=deliv_count
        )

        # Entity 5: projectPublications
        pub_params = {
            "id": ParameterSchema(
                name="id", table="projectPublications", column="id", sql_type="VARCHAR",
                semantic_type=SemanticType.KEYWORD, description="Publication record ID."
            ),
            "title": ParameterSchema(
                name="title", table="projectPublications", column="title", sql_type="VARCHAR",
                semantic_type=SemanticType.TEXT, description="Title of research publication."
            ),
            "authors": ParameterSchema(
                name="authors", table="projectPublications", column="authors", sql_type="VARCHAR",
                semantic_type=SemanticType.TEXT, description="Authors."
            ),
            "journalTitle": ParameterSchema(
                name="journalTitle", table="projectPublications", column="journalTitle", sql_type="VARCHAR",
                semantic_type=SemanticType.KEYWORD, description="Journal name."
            ),
            "publishedYear": ParameterSchema(
                name="publishedYear", table="projectPublications", column="publishedYear", sql_type="INTEGER",
                semantic_type=SemanticType.NUMBER, duckling_dimension=DucklingDimension.TIME,
                description="Year of publication."
            ),
            "doi": ParameterSchema(
                name="doi", table="projectPublications", column="doi", sql_type="VARCHAR",
                semantic_type=SemanticType.KEYWORD, description="DOI."
            ),
            "projectID": ParameterSchema(
                name="projectID", table="projectPublications", column="projectID", sql_type="VARCHAR",
                semantic_type=SemanticType.KEYWORD, description="Associated project ID."
            ),
        }
        pub_count = con.execute("SELECT COUNT(*) FROM projectPublications").fetchone()[0]
        schema.entities["projectPublications"] = EntitySchema(
            name="projectPublications",
            table_name="projectPublications",
            description="Publications and articles resulting from Horizon projects.",
            foreign_keys={"projectID": "project.id"},
            parameters=pub_params,
            row_count=pub_count
        )

        # Joins
        schema.joins = [
            JoinPath(from_entity="project", to_entity="organization", join_clause="project.id = organization.projectID"),
            JoinPath(from_entity="project", to_entity="euroSciVoc", join_clause="project.id = euroSciVoc.projectID"),
            JoinPath(from_entity="project", to_entity="topics", join_clause="project.id = topics.projectID"),
            JoinPath(from_entity="project", to_entity="legalBasis", join_clause="project.id = legalBasis.projectID"),
            JoinPath(from_entity="project", to_entity="projectDeliverables", join_clause="project.id = projectDeliverables.projectID"),
            JoinPath(from_entity="project", to_entity="projectPublications", join_clause="project.id = projectPublications.projectID"),
            JoinPath(from_entity="project", to_entity="reportSummaries", join_clause="project.id = reportSummaries.projectID"),
            JoinPath(from_entity="project", to_entity="policyPriorities", join_clause="project.id = policyPriorities.projectID"),
        ]

        # Vocabularies
        countries = [r[0] for r in con.execute("SELECT DISTINCT country FROM organization WHERE country IS NOT NULL AND country != '' ORDER BY country").fetchall()]
        funding_schemes = [r[0] for r in con.execute("SELECT DISTINCT fundingScheme FROM project WHERE fundingScheme IS NOT NULL AND fundingScheme != '' ORDER BY fundingScheme").fetchall()]
        activity_types = [r[0] for r in con.execute("SELECT DISTINCT activityType FROM organization WHERE activityType IS NOT NULL AND activityType != '' ORDER BY activityType").fetchall()]
        topics = [r[0] for r in con.execute("SELECT DISTINCT euroSciVocTitle FROM euroSciVoc WHERE euroSciVocTitle IS NOT NULL AND euroSciVocTitle != '' ORDER BY euroSciVocTitle").fetchall()]

        schema.vocabularies = {
            "countries": countries,
            "country_names": list(COUNTRY_MAP.values()),
            "funding_schemes": funding_schemes,
            "activity_types": activity_types,
            "euroSciVoc_topics": topics,
            "roles": ["coordinator", "participant", "partner"],
            "status": ["SIGNED", "CLOSED", "TERMINATED"],
        }

        return schema
