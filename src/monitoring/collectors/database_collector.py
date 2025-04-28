"""
Database metrics collector for PostgreSQL, MongoDB, and Redis.

This module provides a collector for monitoring database performance metrics
including connection counts, query performance, cache hit ratios, and more.
"""

import logging
import time
from typing import Dict, List, Optional, Any, Tuple

import psycopg2
import pymongo
import redis
from prometheus_client.core import GaugeMetricFamily, CounterMetricFamily, HistogramMetricFamily

from monitoring.collectors.base_collector import BaseCollector

logger = logging.getLogger(__name__)

class DatabaseCollector(BaseCollector):
    """Collects metrics from PostgreSQL, MongoDB, and Redis databases."""

    def __init__(
        self,
        collection_interval: int = 15,
        postgres_config: Optional[Dict[str, Any]] = None,
        mongodb_config: Optional[Dict[str, Any]] = None,
        redis_config: Optional[Dict[str, Any]] = None
    ):
        """
        Initialize the database collector.

        Args:
            collection_interval: Interval in seconds for metrics collection
            postgres_config: PostgreSQL connection configuration
            mongodb_config: MongoDB connection configuration
            redis_config: Redis connection configuration
        """
        super().__init__(collection_interval=collection_interval)
        self.name = "database_collector"
        
        # Default configurations
        self.postgres_config = postgres_config or {
            "host": "localhost",
            "port": 5432,
            "database": "forex",
            "user": "postgres",
            "password": "postgres"
        }
        
        self.mongodb_config = mongodb_config or {
            "host": "localhost",
            "port": 27017,
            "database": "forex"
        }
        
        self.redis_config = redis_config or {
            "host": "localhost",
            "port": 6379,
            "db": 0
        }
        
        # Connection instances
        self.pg_conn = None
        self.mongo_client = None
        self.redis_client = None
        
        # Metrics
        self.metrics = {}

    def collect_metrics(self) -> List[Any]:
        """Collect metrics from all configured database systems."""
        start_time = time.time()
        metrics = []
        
        try:
            # PostgreSQL metrics
            if self.postgres_config:
                pg_metrics = self._collect_postgres_metrics()
                metrics.extend(pg_metrics)
            
            # MongoDB metrics
            if self.mongodb_config:
                mongo_metrics = self._collect_mongodb_metrics()
                metrics.extend(mongo_metrics)
            
            # Redis metrics
            if self.redis_config:
                redis_metrics = self._collect_redis_metrics()
                metrics.extend(redis_metrics)
                
        except Exception as e:
            logger.error(f"Error collecting database metrics: {str(e)}")
        
        collection_time = time.time() - start_time
        collection_time_metric = GaugeMetricFamily(
            'database_metrics_collection_time_seconds',
            'Time spent collecting database metrics',
            labels=[]
        )
        collection_time_metric.add_metric([], collection_time)
        metrics.append(collection_time_metric)
        
        return metrics

    def _collect_postgres_metrics(self) -> List[Any]:
        """Collect PostgreSQL database metrics."""
        metrics = []
        
        try:
            # Connect to PostgreSQL if not already connected
            if self.pg_conn is None or self.pg_conn.closed:
                self.pg_conn = psycopg2.connect(**self.postgres_config)
            
            # Connection metrics
            connections = GaugeMetricFamily(
                'postgres_connections',
                'PostgreSQL active connections',
                labels=['database', 'state']
            )
            
            with self.pg_conn.cursor() as cursor:
                # Get connection counts by state
                cursor.execute("""
                    SELECT datname, state, count(*)
                    FROM pg_stat_activity
                    GROUP BY datname, state
                """)
                for db, state, count in cursor.fetchall():
                    if state is None:
                        state = 'unknown'
                    connections.add_metric([db, state], count)
                metrics.append(connections)
                
                # Database statistics
                db_stats = GaugeMetricFamily(
                    'postgres_database_stats',
                    'PostgreSQL database statistics',
                    labels=['database', 'statistic']
                )
                
                cursor.execute("""
                    SELECT datname,
                           xact_commit, xact_rollback,
                           blks_read, blks_hit,
                           tup_returned, tup_fetched, tup_inserted, tup_updated, tup_deleted
                    FROM pg_stat_database
                    WHERE datname = %s
                """, (self.postgres_config['database'],))
                
                for row in cursor.fetchall():
                    db = row[0]
                    db_stats.add_metric([db, 'xact_commit'], row[1])
                    db_stats.add_metric([db, 'xact_rollback'], row[2])
                    db_stats.add_metric([db, 'blks_read'], row[3])
                    db_stats.add_metric([db, 'blks_hit'], row[4])
                    db_stats.add_metric([db, 'tup_returned'], row[5])
                    db_stats.add_metric([db, 'tup_fetched'], row[6])
                    db_stats.add_metric([db, 'tup_inserted'], row[7])
                    db_stats.add_metric([db, 'tup_updated'], row[8])
                    db_stats.add_metric([db, 'tup_deleted'], row[9])
                
                metrics.append(db_stats)
                
                # Calculate cache hit ratio
                cache_hit_ratio = GaugeMetricFamily(
                    'postgres_cache_hit_ratio',
                    'PostgreSQL cache hit ratio',
                    labels=['database']
                )
                
                cursor.execute("""
                    SELECT datname,
                           CASE WHEN blks_hit + blks_read = 0 THEN 0
                                ELSE blks_hit::float / (blks_hit + blks_read)
                           END AS cache_hit_ratio
                    FROM pg_stat_database
                    WHERE datname = %s
                """, (self.postgres_config['database'],))
                
                for db, ratio in cursor.fetchall():
                    cache_hit_ratio.add_metric([db], ratio)
                metrics.append(cache_hit_ratio)
                
                # Table statistics
                table_stats = GaugeMetricFamily(
                    'postgres_table_stats',
                    'PostgreSQL table statistics',
                    labels=['table', 'statistic']
                )
                
                cursor.execute("""
                    SELECT relname,
                           seq_scan, seq_tup_read,
                           idx_scan, idx_tup_fetch,
                           n_tup_ins, n_tup_upd, n_tup_del
                    FROM pg_stat_user_tables
                    ORDER BY relname
                """)
                
                for row in cursor.fetchall():
                    table = row[0]
                    table_stats.add_metric([table, 'seq_scan'], row[1])
                    table_stats.add_metric([table, 'seq_tup_read'], row[2])
                    table_stats.add_metric([table, 'idx_scan'], row[3] if row[3] is not None else 0)
                    table_stats.add_metric([table, 'idx_tup_fetch'], row[4] if row[4] is not None else 0)
                    table_stats.add_metric([table, 'n_tup_ins'], row[5])
                    table_stats.add_metric([table, 'n_tup_upd'], row[6])
                    table_stats.add_metric([table, 'n_tup_del'], row[7])
                
                metrics.append(table_stats)
                
                # Index usage statistics
                index_stats = GaugeMetricFamily(
                    'postgres_index_stats',
                    'PostgreSQL index statistics',
                    labels=['table', 'index', 'statistic']
                )
                
                cursor.execute("""
                    SELECT
                        t.relname AS table,
                        i.relname AS index,
                        s.idx_scan,
                        s.idx_tup_read,
                        s.idx_tup_fetch
                    FROM
                        pg_stat_user_indexes s
                        JOIN pg_class t ON t.oid = s.relid
                        JOIN pg_class i ON i.oid = s.indexrelid
                    ORDER BY t.relname, i.relname
                """)
                
                for table, index, idx_scan, idx_tup_read, idx_tup_fetch in cursor.fetchall():
                    index_stats.add_metric([table, index, 'idx_scan'], idx_scan)
                    index_stats.add_metric([table, index, 'idx_tup_read'], idx_tup_read)
                    index_stats.add_metric([table, index, 'idx_tup_fetch'], idx_tup_fetch)
                
                metrics.append(index_stats)
                
        except Exception as e:
            logger.error(f"Error collecting PostgreSQL metrics: {str(e)}")
            # Create connection status metric
            pg_status = GaugeMetricFamily(
                'postgres_connection_status',
                'PostgreSQL connection status (1=connected, 0=disconnected)',
                labels=[]
            )
            pg_status.add_metric([], 0)
            metrics.append(pg_status)
        else:
            # Add connection status metric
            pg_status = GaugeMetricFamily(
                'postgres_connection_status',
                'PostgreSQL connection status (1=connected, 0=disconnected)',
                labels=[]
            )
            pg_status.add_metric([], 1)
            metrics.append(pg_status)
            
        return metrics

    def _collect_mongodb_metrics(self) -> List[Any]:
        """Collect MongoDB database metrics."""
        metrics = []
        
        try:
            # Connect to MongoDB if not already connected
            if self.mongo_client is None:
                self.mongo_client = pymongo.MongoClient(
                    host=self.mongodb_config.get('host'),
                    port=self.mongodb_config.get('port'),
                    serverSelectionTimeoutMS=5000  # 5 second timeout for server selection
                )
            
            # Test connection
            self.mongo_client.admin.command('ping')
            
            # Server status
            server_status = self.mongo_client.admin.command('serverStatus')
            
            # Connection pool metrics
            conn_metrics = GaugeMetricFamily(
                'mongodb_connections',
                'MongoDB connection statistics',
                labels=['state']
            )
            connections = server_status.get('connections', {})
            
            conn_metrics.add_metric(['current'], connections.get('current', 0))
            conn_metrics.add_metric(['available'], connections.get('available', 0))
            conn_metrics.add_metric(['totalCreated'], connections.get('totalCreated', 0))
            metrics.append(conn_metrics)
            
            # Operation metrics
            op_metrics = GaugeMetricFamily(
                'mongodb_operations',
                'MongoDB operation counters',
                labels=['type']
            )
            
            opcounters = server_status.get('opcounters', {})
            for op_type, count in opcounters.items():
                op_metrics.add_metric([op_type], count)
            metrics.append(op_metrics)
            
            # Memory metrics
            mem_metrics = GaugeMetricFamily(
                'mongodb_memory_usage',
                'MongoDB memory usage in bytes',
                labels=['type']
            )
            
            mem = server_status.get('mem', {})
            mem_metrics.add_metric(['resident'], mem.get('resident', 0) * 1024 * 1024)  # Convert to bytes
            mem_metrics.add_metric(['virtual'], mem.get('virtual', 0) * 1024 * 1024)  # Convert to bytes
            mem_metrics.add_metric(['mapped'], mem.get('mapped', 0) * 1024 * 1024 if 'mapped' in mem else 0)  # Convert to bytes
            metrics.append(mem_metrics)
            
            # Database statistics
            db = self.mongo_client[self.mongodb_config.get('database', 'forex')]
            db_stats = db.command('dbStats')
            
            db_size_metrics = GaugeMetricFamily(
                'mongodb_database_stats',
                'MongoDB database statistics',
                labels=['database', 'type']
            )
            
            db_name = self.mongodb_config.get('database', 'forex')
            db_size_metrics.add_metric([db_name, 'collections'], db_stats.get('collections', 0))
            db_size_metrics.add_metric([db_name, 'views'], db_stats.get('views', 0))
            db_size_metrics.add_metric([db_name, 'objects'], db_stats.get('objects', 0))
            db_size_metrics.add_metric([db_name, 'indexes'], db_stats.get('indexes', 0))
            db_size_metrics.add_metric([db_name, 'dataSize'], db_stats.get('dataSize', 0))
            db_size_metrics.add_metric([db_name, 'storageSize'], db_stats.get('storageSize', 0))
            db_size_metrics.add_metric([db_name, 'indexSize'], db_stats.get('indexSize', 0))
            metrics.append(db_size_metrics)
            
            # Collection metrics
            collection_metrics = GaugeMetricFamily(
                'mongodb_collection_stats',
                'MongoDB collection statistics',
                labels=['database', 'collection', 'type']
            )
            
            for collection_name in db.list_collection_names():
                try:
                    coll_stats = db.command('collStats', collection_name)
                    collection_metrics.add_metric([db_name, collection_name, 'count'], coll_stats.get('count', 0))
                    collection_metrics.add_metric([db_name, collection_name, 'size'], coll_stats.get('size', 0))
                    collection_metrics.add_metric([db_name, collection_name, 'storageSize'], coll_stats.get('storageSize', 0))
                    collection_metrics.add_metric([db_name, collection_name, 'totalIndexSize'], coll_stats.get('totalIndexSize', 0))
                except Exception as e:
                    logger.error(f"Error collecting stats for MongoDB collection {collection_name}: {str(e)}")
            
            metrics.append(collection_metrics)
            
        except Exception as e:
            logger.error(f"Error collecting MongoDB metrics: {str(e)}")
            # Create connection status metric
            mongo_status = GaugeMetricFamily(
                'mongodb_connection_status',
                'MongoDB connection status (1=connected, 0=disconnected)',
                labels=[]
            )
            mongo_status.add_metric([], 0)
            metrics.append(mongo_status)
        else:
            # Add connection status metric
            mongo_status = GaugeMetricFamily(
                'mongodb_connection_status',
                'MongoDB connection status (1=connected, 0=disconnected)',
                labels=[]
            )
            mongo_status.add_metric([], 1)
            metrics.append(mongo_status)
            
        return metrics

    def _collect_redis_metrics(self) -> List[Any]:
        """Collect Redis database metrics."""
        metrics = []
        
        try:
            # Connect to Redis if not already connected
            if self.redis_client is None:
                self.redis_client = redis.Redis(
                    host=self.redis_config.get('host'),
                    port=self.redis_config.get('port'),
                    db=self.redis_config.get('db', 0),
                    socket_timeout=5.0
                )
            
            # Test connection
            self.redis_client.ping()
            
            # Get Redis info
            info = self.redis_client.info()
            
            # Memory metrics
            memory_metrics = GaugeMetricFamily(
                'redis_memory',
                'Redis memory statistics in bytes',
                labels=['type']
            )
            
            memory_metrics.add_metric(['used'], info.get('used_memory', 0))
            memory_metrics.add_metric(['peak'], info.get('used_memory_peak', 0))
            memory_metrics.add_metric(['lua'], info.get('used_memory_lua', 0))
            memory_metrics.add_metric(['rss'], info.get('used_memory_rss', 0))
            metrics.append(memory_metrics)
            
            # Client metrics
            client_metrics = GaugeMetricFamily(
                'redis_clients',
                'Redis client statistics',
                labels=['type']
            )
            
            clients = info.get('clients', {})
            client_metrics.add_metric(['connected'], clients.get('connected_clients', 0))
            client_metrics.add_metric(['blocked'], clients.get('blocked_clients', 0))
            metrics.append(client_metrics)
            
            # Connection metrics
            connection_metrics = GaugeMetricFamily(
                'redis_connections',
                'Redis connection statistics',
                labels=['type']
            )
            
            connection_metrics.add_metric(['total_received'], info.get('total_connections_received', 0))
            connection_metrics.add_metric(['rejected'], info.get('rejected_connections', 0))
            metrics.append(connection_metrics)
            
            # Command metrics
            command_metrics = GaugeMetricFamily(
                'redis_commands',
                'Redis command statistics',
                labels=['type']
            )
            
            command_metrics.add_metric(['processed'], info.get('total_commands_processed', 0))
            metrics.append(command_metrics)
            
            # Keys metrics
            keyspace_metrics = GaugeMetricFamily(
                'redis_keys',
                'Redis keyspace statistics',
                labels=['db', 'type']
            )
            
            # Collect keyspace metrics for all databases
            for db_name, db_stats in info.items():
                if db_name.startswith('db'):
                    # Parse keyspace stats
                    if isinstance(db_stats, str):
                        # Format is "keys=123,expires=456,avg_ttl=789"
                        stats_parts = db_stats.split(',')
                        stats_dict = {}
                        for part in stats_parts:
                            if '=' in part:
                                k, v = part.split('=')
                                try:
                                    stats_dict[k] = int(v)
                                except ValueError:
                                    stats_dict[k] = 0
                        
                        # Add metrics
                        keyspace_metrics.add_metric([db_name, 'keys'], stats_dict.get('keys', 0))
                        keyspace_metrics.add_metric([db_name, 'expires'], stats_dict.get('expires', 0))
                        keyspace_metrics.add_metric([db_name, 'avg_ttl'], stats_dict.get('avg_ttl', 0))
                    elif isinstance(db_stats, dict):
                        # Some Redis versions return dictionaries directly
                        keyspace_metrics.add_metric([db_name, 'keys'], db_stats.get('keys', 0))
                        keyspace_metrics.add_metric([db_name, 'expires'], db_stats.get('expires', 0))
                        keyspace_metrics.add_metric([db_name, 'avg_ttl'], db_stats.get('avg_ttl', 0))
            
            metrics.append(keyspace_metrics)
            
            # Performance metrics
            perf_metrics = GaugeMetricFamily(
                'redis_performance',
                'Redis performance metrics',
                labels=['type']
            )
            
            perf_metrics.add_metric(['instantaneous_ops_per_sec'], info.get('instantaneous_ops_per_sec', 0))
            perf_metrics.add_metric(['hit_rate'], 
                                   0 if info.get('keyspace_hits', 0) + info.get('keyspace_misses', 0) == 0 
                                   else info.get('keyspace_hits', 0) / (info.get('keyspace_hits', 0) + info.get('keyspace_misses', 0)))
            perf_metrics.add_metric(['keyspace_hits'], info.get('keyspace_hits', 0))
            perf_metrics.add_metric(['keyspace_misses'], info.get('keyspace_misses', 0))
            metrics.append(perf_metrics)
            
        except Exception as e:
            logger.error(f"Error collecting Redis metrics: {str(e)}")
            # Create connection status metric
            redis_status = GaugeMetricFamily(
                'redis_connection_status',
                'Redis connection status (1=connected, 0=disconnected)',
                labels=[]
            )
            redis_status.add_metric([], 0)
            metrics.append(redis_status)
        else:
            # Add connection status metric
            redis_status = GaugeMetricFamily(
                'redis_connection_status',
                'Redis connection status (1=connected, 0=disconnected)',
                labels=[]
            )
            redis_status.add_metric([], 1)
            metrics.append(redis_status)
            
        return metrics
    
    def close(self):
        """Close all database connections."""
        try:
            if self.pg_conn is not None:
                self.pg_conn.close()
                self.pg_conn = None
        except Exception as e:
            logger.error(f"Error closing PostgreSQL connection: {str(e)}")
            
        try:
            if self.mongo_client is not None:
                self.mongo_client.close()
                self.mongo_client = None
        except Exception as e:
            logger.error(f"Error closing MongoDB connection: {str(e)}")
            
        try:
            if self.redis_client is not None:
                self.redis_client.close()
                self.redis_client = None
        except Exception as e:
            logger.error(f"Error closing Redis connection: {str(e)}") 