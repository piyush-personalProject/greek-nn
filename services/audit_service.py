# services/audit_service.py
"""
Audit Service for News-to-Greeks Traceability

Provides SQLite in-memory database persistence for the full pipeline:
NewsEvent → EventVector → VolShock → VolSurface → GreeksSnapshot

The trace_id links all stages for end-to-end audit retrieval.
"""
import sqlite3
import json
from datetime import datetime
from typing import Optional, List, Dict, Any
from contextlib import contextmanager
import threading

from schemas import NewsEvent, EventVector, VolShock, VolSurface, Greeks, PortfolioGreeks
from logger import get_logger

logger = get_logger(__name__)

# Thread-local storage for connections
_local = threading.local()


class AuditService:
    """
    SQLite in-memory audit trail for news-to-Greeks traceability.
    
    Maintains a trace_id that links all pipeline stages together.
    Each stage is persisted as it's processed, enabling full audit retrieval.
    """
    
    def __init__(self, db_path: str = ":memory:"):
        """
        Initialize audit service with SQLite database.
        
        Args:
            db_path: SQLite database path. Use ":memory:" for in-memory.
        """
        self.db_path = db_path
        self._init_db()
    
    def _get_connection(self) -> sqlite3.Connection:
        """Get thread-local connection."""
        if not hasattr(_local, 'conn') or _local.conn is None:
            # Use shared cache for in-memory to allow cross-thread sharing
            if self.db_path == ":memory:":
                conn = sqlite3.connect("file::memory:?cache=shared", uri=True, check_same_thread=False)
            else:
                conn = sqlite3.connect(self.db_path, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            _local.conn = conn
        return _local.conn
    
    @contextmanager
    def _cursor(self):
        """Context manager for database cursor."""
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            yield cursor
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            cursor.close()
    
    def _init_db(self):
        """Initialize database schema."""
        with self._cursor() as cursor:
            # Trace metadata
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS traces (
                    trace_id TEXT PRIMARY KEY,
                    created_at TIMESTAMP NOT NULL,
                    status TEXT DEFAULT 'active',
                    completed_at TIMESTAMP,
                    metadata TEXT
                )
            """)
            
            # News events
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS news_events (
                    trace_id TEXT NOT NULL,
                    headline TEXT NOT NULL,
                    source TEXT NOT NULL,
                    url TEXT,
                    published_at TIMESTAMP,
                    content TEXT,
                    importance TEXT,
                    ingested_at TIMESTAMP NOT NULL,
                    FOREIGN KEY (trace_id) REFERENCES traces(trace_id)
                )
            """)
            
            # Event vectors (NLP output)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS event_vectors (
                    trace_id TEXT NOT NULL,
                    event_id TEXT PRIMARY KEY,
                    headline TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    sentiment TEXT NOT NULL,
                    sentiment_score REAL,
                    importance REAL,
                    surprise_factor REAL,
                    entities TEXT,
                    processed_at TIMESTAMP,
                    source TEXT,
                    FOREIGN KEY (trace_id) REFERENCES traces(trace_id)
                )
            """)
            
            # Vol shocks
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS vol_shocks (
                    trace_id TEXT NOT NULL,
                    shock_id TEXT PRIMARY KEY,
                    event_id TEXT NOT NULL,
                    delta_1W_ATM REAL,
                    delta_1M_ATM REAL,
                    delta_3M_ATM REAL,
                    delta_6M_ATM REAL,
                    delta_1Y_ATM REAL,
                    delta_1M_25RR REAL,
                    delta_1M_25BF REAL,
                    predicted_at TIMESTAMP,
                    model_version TEXT,
                    FOREIGN KEY (trace_id) REFERENCES traces(trace_id),
                    FOREIGN KEY (event_id) REFERENCES event_vectors(event_id)
                )
            """)
            
            # Vol surfaces
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS vol_surfaces (
                    trace_id TEXT NOT NULL,
                    snapshot_id TEXT PRIMARY KEY,
                    shock_id TEXT,
                    base_date TIMESTAMP,
                    tenors TEXT,
                    strikes TEXT,
                    volatilities TEXT,
                    source TEXT,
                    version TEXT,
                    created_at TIMESTAMP NOT NULL,
                    FOREIGN KEY (trace_id) REFERENCES traces(trace_id),
                    FOREIGN KEY (shock_id) REFERENCES vol_shocks(shock_id)
                )
            """)
            
            # Greeks snapshots
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS greeks_snapshots (
                    trace_id TEXT NOT NULL,
                    snapshot_id TEXT PRIMARY KEY,
                    portfolio_id TEXT NOT NULL,
                    vol_surface_snapshot_id TEXT,
                    delta REAL,
                    gamma REAL,
                    vega REAL,
                    theta REAL,
                    rho REAL,
                    vanna REAL,
                    volga REAL,
                    computed_at TIMESTAMP NOT NULL,
                    FOREIGN KEY (trace_id) REFERENCES traces(trace_id),
                    FOREIGN KEY (vol_surface_snapshot_id) REFERENCES vol_surfaces(snapshot_id)
                )
            """)
            
            # Indexes for fast lookups
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_traces_status ON traces(status)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_news_trace ON news_events(trace_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_vectors_trace ON event_vectors(trace_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_shocks_trace ON vol_shocks(trace_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_surfaces_trace ON vol_surfaces(trace_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_greeks_trace ON greeks_snapshots(trace_id)")
        
        logger.info("Audit database initialized")
    
    def begin_trace(self, trace_id: str, metadata: Optional[Dict] = None) -> str:
        """
        Begin a new trace for a pipeline run.
        
        Args:
            trace_id: Unique trace identifier
            metadata: Optional metadata dict
            
        Returns:
            trace_id
        """
        with self._cursor() as cursor:
            cursor.execute("""
                INSERT OR REPLACE INTO traces (trace_id, created_at, status, metadata)
                VALUES (?, ?, 'active', ?)
            """, (trace_id, datetime.now().isoformat(), sqlite3.dumps(metadata) if metadata else None))
        
        logger.info(f"Trace started: {trace_id}")
        return trace_id
    
    def end_trace(self, trace_id: str, status: str = "completed"):
        """Mark trace as completed."""
        with self._cursor() as cursor:
            cursor.execute("""
                UPDATE traces SET status = ?, completed_at = ? WHERE trace_id = ?
            """, (status, datetime.now().isoformat(), trace_id))
        
        logger.info(f"Trace {trace_id} ended with status: {status}")
    
    def persist_news_event(self, trace_id: str, event: NewsEvent) -> str:
        """
        Persist a news event to the audit trail.
        
        Args:
            trace_id: Trace identifier
            event: NewsEvent instance
            
        Returns:
            trace_id
        """
        with self._cursor() as cursor:
            cursor.execute("""
                INSERT INTO news_events 
                (trace_id, headline, source, url, published_at, content, importance, ingested_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                trace_id, 
                event.headline, 
                event.source, 
                event.url,
                event.published_at.isoformat() if event.published_at else None,
                event.content,
                event.importance,
                datetime.now().isoformat()
            ))
        
        logger.debug(f"News event persisted for trace: {trace_id}")
        return trace_id
    
    def persist_event_vector(self, trace_id: str, vector: EventVector) -> str:
        """
        Persist an event vector to the audit trail.
        
        Args:
            trace_id: Trace identifier
            vector: EventVector instance
            
        Returns:
            event_id
        """
        with self._cursor() as cursor:
            cursor.execute("""
                INSERT OR REPLACE INTO event_vectors
                (trace_id, event_id, headline, event_type, sentiment, sentiment_score,
                 importance, surprise_factor, entities, processed_at, source)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                trace_id,
                vector.event_id,
                vector.headline,
                vector.event_type.value,
                vector.sentiment.value,
                vector.sentiment_score,
                vector.importance,
                vector.surprise_factor,
                json.dumps(vector.entities),
                vector.processed_at.isoformat(),
                vector.source
            ))
        
        logger.debug(f"Event vector persisted: {vector.event_id}")
        return vector.event_id
    
    def persist_vol_shock(self, trace_id: str, shock: VolShock) -> str:
        """
        Persist a vol shock to the audit trail.
        
        Args:
            trace_id: Trace identifier
            shock: VolShock instance
            
        Returns:
            shock_id
        """
        with self._cursor() as cursor:
            cursor.execute("""
                INSERT OR REPLACE INTO vol_shocks
                (trace_id, shock_id, event_id, delta_1W_ATM, delta_1M_ATM, delta_3M_ATM,
                 delta_6M_ATM, delta_1Y_ATM, delta_1M_25RR, delta_1M_25BF, predicted_at, model_version)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                trace_id,
                shock.shock_id,
                shock.event_vector.event_id,
                shock.delta_1W_ATM,
                shock.delta_1M_ATM,
                shock.delta_3M_ATM,
                shock.delta_6M_ATM,
                shock.delta_1Y_ATM,
                shock.delta_1M_25RR,
                shock.delta_1M_25BF,
                shock.predicted_at.isoformat(),
                shock.model_version
            ))
        
        logger.debug(f"Vol shock persisted: {shock.shock_id}")
        return shock.shock_id
    
    def persist_vol_surface(self, trace_id: str, shock_id: str, surface: VolSurface) -> str:
        """
        Persist a vol surface to the audit trail.
        
        Args:
            trace_id: Trace identifier
            shock_id: Associated vol shock ID
            surface: VolSurface instance
            
        Returns:
            snapshot_id
        """
        with self._cursor() as cursor:
            cursor.execute("""
                INSERT OR REPLACE INTO vol_surfaces
                (trace_id, snapshot_id, shock_id, base_date, tenors, strikes, volatilities, source, version, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                trace_id,
                surface.snapshot_id,
                shock_id,
                surface.base_date.isoformat(),
                json.dumps(surface.tenors),
                json.dumps(surface.strikes),
                json.dumps(surface.volatilities),
                surface.source,
                surface.version,
                datetime.now().isoformat()
            ))
        
        logger.debug(f"Vol surface persisted: {surface.snapshot_id}")
        return surface.snapshot_id
    
    def persist_greeks(self, trace_id: str, portfolio_id: str, vol_surface_snapshot_id: Optional[str],
                       greeks: Greeks, snapshot_id: str) -> str:
        """
        Persist Greeks to the audit trail.
        
        Args:
            trace_id: Trace identifier
            portfolio_id: Portfolio identifier
            vol_surface_snapshot_id: Associated vol surface snapshot ID
            greeks: Greeks instance
            snapshot_id: Unique snapshot identifier
            
        Returns:
            snapshot_id
        """
        with self._cursor() as cursor:
            cursor.execute("""
                INSERT OR REPLACE INTO greeks_snapshots
                (trace_id, snapshot_id, portfolio_id, vol_surface_snapshot_id,
                 delta, gamma, vega, theta, rho, vanna, volga, computed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                trace_id,
                snapshot_id,
                portfolio_id,
                vol_surface_snapshot_id,
                greeks.delta,
                greeks.gamma,
                greeks.vega,
                greeks.theta,
                greeks.rho,
                greeks.vanna,
                greeks.volga,
                datetime.now().isoformat()
            ))
        
        logger.debug(f"Greeks persisted: {snapshot_id}")
        return snapshot_id
    
    def get_trace(self, trace_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve full trace with all linked data.
        
        Args:
            trace_id: Trace identifier
            
        Returns:
            Dict with trace, news_events, event_vectors, vol_shocks, vol_surfaces, greeks
        """
        with self._cursor() as cursor:
            # Get trace metadata
            cursor.execute("SELECT * FROM traces WHERE trace_id = ?", (trace_id,))
            trace_row = cursor.fetchone()
            
            if not trace_row:
                return None
            
            result = {
                'trace': dict(trace_row),
                'news_events': [],
                'event_vectors': [],
                'vol_shocks': [],
                'vol_surfaces': [],
                'greeks_snapshots': []
            }
            
            # Get news events
            cursor.execute("SELECT * FROM news_events WHERE trace_id = ?", (trace_id,))
            for row in cursor.fetchall():
                result['news_events'].append(dict(row))
            
            # Get event vectors
            cursor.execute("SELECT * FROM event_vectors WHERE trace_id = ?", (trace_id,))
            for row in cursor.fetchall():
                vec = dict(row)
                vec['entities'] = json.loads(vec['entities']) if vec['entities'] else {}
                result['event_vectors'].append(vec)
            
            # Get vol shocks
            cursor.execute("SELECT * FROM vol_shocks WHERE trace_id = ?", (trace_id,))
            for row in cursor.fetchall():
                result['vol_shocks'].append(dict(row))
            
            # Get vol surfaces
            cursor.execute("SELECT * FROM vol_surfaces WHERE trace_id = ?", (trace_id,))
            for row in cursor.fetchall():
                surf = dict(row)
                surf['tenors'] = json.loads(surf['tenors'])
                surf['strikes'] = json.loads(surf['strikes'])
                surf['volatilities'] = json.loads(surf['volatilities'])
                result['vol_surfaces'].append(surf)
            
            # Get Greeks snapshots
            cursor.execute("SELECT * FROM greeks_snapshots WHERE trace_id = ?", (trace_id,))
            for row in cursor.fetchall():
                result['greeks_snapshots'].append(dict(row))
            
            return result
    
    def get_recent_traces(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent traces."""
        with self._cursor() as cursor:
            cursor.execute("""
                SELECT * FROM traces 
                ORDER BY created_at DESC 
                LIMIT ?
            """, (limit,))
            
            return [dict(row) for row in cursor.fetchall()]
    
    def get_active_traces(self) -> List[Dict[str, Any]]:
        """Get all active traces."""
        with self._cursor() as cursor:
            cursor.execute("""
                SELECT * FROM traces 
                WHERE status = 'active'
                ORDER BY created_at DESC
            """)
            
            return [dict(row) for row in cursor.fetchall()]


# Singleton instance
_audit_service: Optional[AuditService] = None


def get_audit_service() -> AuditService:
    """Get the global audit service instance."""
    global _audit_service
    if _audit_service is None:
        _audit_service = AuditService()
    return _audit_service


def init_audit_service(db_path: str = ":memory:") -> AuditService:
    """Initialize the global audit service."""
    global _audit_service
    _audit_service = AuditService(db_path)
    return _audit_service
