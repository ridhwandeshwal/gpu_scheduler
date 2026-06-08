-- Seed data for local development/testing
-- Matches the actual hardware on this machine:
--   1x NVIDIA GeForce RTX 4060 Max-Q (8GB)
--   24 CPU cores, ~16GB RAM

INSERT INTO compute_nodes (id, node_name, hostname, total_gpus, total_cpu_cores, total_memory_mb, is_active, last_heartbeat_at)
VALUES (
    'a0000000-0000-0000-0000-000000000001',
    'dev-node-01',
    'ubuntu',
    1,
    24,
    15681,
    TRUE,
    NOW()
);

INSERT INTO gpu_devices (id, node_id, gpu_index, gpu_model, gpu_memory_mb, status)
VALUES (
    'b0000000-0000-0000-0000-000000000001',
    'a0000000-0000-0000-0000-000000000001',
    0,
    'NVIDIA GeForce RTX 4060 Max-Q',
    8192,
    'available'
);
