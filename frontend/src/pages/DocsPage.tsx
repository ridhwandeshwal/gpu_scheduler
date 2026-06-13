import { Stack, Title, Text, Paper, Code, List, Alert, Group, ActionIcon, CopyButton, Tooltip, Divider, Badge, Box } from '@mantine/core';
import { Info, Copy, Check, Sparkles } from 'lucide-react';

export function DocsPage() {
  const agentSkillMarkdown = `---
name: "GPU Job Submission"
description: "Submit and structure PyTorch/ML jobs for the remote sandboxed GPU scheduler"
version: "1.0.0"
---

# GPU Job Submission Skill

## Context
This platform executes user-submitted code in an isolated Docker sandbox. You do not have interactive terminal access during execution. Your job is to package the user's code into a cohesive script or repository that runs completely autonomously.

## Container Configuration & Constraints
1. **Base Image:** \`python:3.11-slim\`
2. **Privileges:** The container runs as a non-root user. You CANNOT use \`sudo\`, \`apt-get\`, or modify system files.
3. **Filesystem:** The root filesystem and \`/workspace\` are strictly **read-only**.
4. **Writable Paths:** You can only write to \`/tmp\` (RAM), \`/outputs\` (NAS), and \`./data\` (which symlinks to \`/outputs/data\`).
5. **Python Dependencies:** A provided \`requirements.txt\` is automatically pip-installed into a persistent user-space directory. Do not run \`pip install\` manually in the scripts.

## Rules & Formatting
1. **Data Directory Enforcement:** You MUST instruct scripts to download or save all datasets/models to \`./data\`. The platform intercepts this folder, stores it on a high-speed NAS, and excludes it from the final artifact bundle to save space. Do NOT save datasets to the root directory.
2. **Resource Selection:** When submitting the job:
   - Request \`1\` GPU for ML training workloads.
   - Request \`0\` GPUs for purely CPU tasks.
3. **No Interactive Prompts:** Ensure the code does not block waiting for user input (\`input()\`, \`y/n\` prompts).
4. **Environment Variables:** Use the job submission form's Environment Variables section to securely pass API keys or configuration. DO NOT hardcode secrets in the script.

## Usage Instructions for Agents
1. Navigate to the **New Job** form in the UI.
2. If writing a single file, use the **Python / Shell Script** tab. Provide an optional \`requirements.txt\` and a setup shell script.
3. If using a repo, use the **GitHub Repository** tab. Provide the URL, Branch, and the relative path to the entrypoint script.
`;

  return (
    <Stack gap="xl" pb="xl" maw={1200} mx="auto">
      <Box>
        <Title order={2} mb="xs">Documentation</Title>
        <Text c="dimmed">Complete guide to structuring, submitting, and retrieving workloads on the GPU Scheduler.</Text>
      </Box>

      <Paper p="lg" radius="md" withBorder>
        <Title order={4} mb="sm">1. Execution Environment</Title>
        <Text size="sm" mb="sm">
          Every job is executed inside a fully isolated, headless Docker container. 
          There is no interactive terminal access once a job starts. All code must run autonomously from start to finish.
        </Text>
        <List size="sm" mb="md">
          <List.Item><b>Base Image:</b> Jobs run on <code>python:3.11-slim</code> by default.</List.Item>
          <List.Item><b>Security & Privileges:</b> The container executes as a restricted non-root user. System-wide installations (like <code>apt-get</code>) are not permitted.</List.Item>
          <List.Item><b>Read-Only Filesystem:</b> To ensure reproducibility and security, the container's root filesystem and your <code>/workspace</code> are completely read-only. If you need to write temporary files, use <code>/tmp</code> (RAM-backed), or write to <code>/outputs</code> for permanent storage.</List.Item>
        </List>
        <Alert icon={<Info size={16} />} title="The Data Directory Rule" color="blue" variant="light" mb="md">
          Always download external datasets and large models into the <code>./data</code> directory relative to your workspace. 
          The scheduler automatically routes this directory to a high-speed, scalable NAS volume and explicitly excludes it from artifact collection. 
          This keeps your job's final artifact bundle lightweight and prevents object storage bloat.
        </Alert>
      </Paper>

      <Paper p="lg" radius="md" withBorder>
        <Title order={4} mb="sm">2. Job Submission Modes</Title>
        
        <Title order={6} mt="md" mb="xs">Python / Shell Script</Title>
        <Text size="sm" mb="sm" c="dimmed">
          Ideal for quick experiments or standalone scripts. You upload a single main <code>.py</code> file.
        </Text>
        <List size="sm" mb="md">
          <List.Item><b>Python Script:</b> The primary script that will be executed.</List.Item>
          <List.Item><b>requirements.txt</b> <i>(Optional)</i>: Dependencies listed here are automatically installed via <code>pip</code> into a persistent cache before your script runs.</List.Item>
          <List.Item><b>Setup Script</b> <i>(Optional)</i>: A <code>.sh</code> file executed before your Python script. Perfect for downloading weights, preprocessing files, or custom user-space environment setup.</List.Item>
        </List>

        <Divider my="md" />

        <Title order={6} mb="xs">GitHub Repository</Title>
        <Text size="sm" mb="sm" c="dimmed">
          For larger, multi-file projects. The worker performs a clean clone of your repository directly into the sandbox.
        </Text>
        <List size="sm">
          <List.Item><b>GitHub Repo URL:</b> The HTTPS URL to clone.</List.Item>
          <List.Item><b>Branch:</b> Defaults to <code>main</code>, but you can specify any valid branch.</List.Item>
          <List.Item><b>Entrypoint:</b> The path to the script to run (e.g., <code>src/train.py</code> or <code>main.sh</code>).</List.Item>
          <List.Item><b>Run as module:</b> Check this if your project relies on absolute or relative module imports. It executes the entrypoint as a module (e.g., running <code>python -m src.train</code> instead of <code>python src/train.py</code>).</List.Item>
          <List.Item><b>Subdirectory:</b> <i>(Optional)</i> If your Python project is nested inside a subfolder of the repository (like <code>backend/</code>), provide it here so the scheduler sets the correct working directory before execution.</List.Item>
          <List.Item><b>Commit Hash:</b> <i>(Optional)</i> Pin your job to a specific commit hash for exact reproducibility.</List.Item>
          <List.Item><b>Requirements File Path:</b> <i>(Optional)</i> The relative path to your <code>requirements.txt</code> inside the cloned repository.</List.Item>
        </List>
      </Paper>

      <Paper p="lg" radius="md" withBorder>
        <Title order={4} mb="sm">3. Resources & Environment</Title>
        <List size="sm" spacing="xs" mb="md">
          <List.Item>
            <b>GPUs:</b> Select <Badge size="xs" variant="light">0</Badge> for purely CPU-bound jobs, or <Badge size="xs" variant="light">1</Badge> to request exclusive access to a hardware-isolated GPU.
          </List.Item>
          <List.Item>
            <b>Environment Variables:</b> Pass API keys (like Weights & Biases tokens) and configuration parameters securely. Toggle the "Secret" switch to mask the value in the UI and prevent it from being exposed.
          </List.Item>
          <List.Item>
            <b>Priority:</b> <i>(Admins only)</i> Manually override the scheduling queue priority scale (1-10) to fast-track critical workloads.
          </List.Item>
        </List>
      </Paper>

      <Paper p="lg" radius="md" withBorder>
        <Title order={4} mb="sm">4. Logs, Outputs, & Artifacts</Title>
        
        <Title order={6} mt="md" mb="xs">Logging System</Title>
        <Text size="sm" mb="sm" c="dimmed">
          You don't need to manually configure log writing. The scheduler hooks directly into the Docker streams.
        </Text>
        <List size="sm" mb="md">
          <List.Item>Clicking on any job in the <b>My Jobs</b> table opens the Job Drawer.</List.Item>
          <List.Item>The backend automatically records your code's raw <code>stdout</code> and <code>stderr</code> streams.</List.Item>
          <List.Item>A <b>Combined Log</b> is generated, giving you a perfectly time-synchronized view of both standard output and error messages.</List.Item>
        </List>

        <Divider my="md" />

        <Title order={6} mb="xs">Personalized Artifacts Storage</Title>
        <Text size="sm" mb="sm" c="dimmed">
          Your outputs are preserved in an isolated object storage bucket on a per-run basis.
        </Text>
        <List size="sm">
          <List.Item>When a job finishes executing (or fails gracefully), the scheduler takes a snapshot of your workspace.</List.Item>
          <List.Item>Any file created or modified by your script (excluding the aforementioned <code>./data</code> directory) is automatically detected, checksummed with SHA-256, and uploaded to the centralized MinIO Object Storage.</List.Item>
          <List.Item>Navigate to the <b>Artifacts</b> page in the sidebar. This page acts as your personalized object storage explorer. You can drill down into any historical job run, view exactly what files were generated, verify their file sizes and checksums, and securely download them back to your local machine.</List.Item>
        </List>
      </Paper>

      <Paper p="lg" radius="md" withBorder>
        <Group justify="space-between" mb="sm">
          <Group gap="xs">
            <Sparkles size={20} color="var(--mantine-color-violet-6)" />
            <Title order={4}>Agent Skill (agentskills.io)</Title>
          </Group>
          <CopyButton value={agentSkillMarkdown} timeout={2000}>
            {({ copied, copy }) => (
              <Tooltip label={copied ? 'Copied' : 'Copy Skill Markdown'} withArrow position="left">
                <ActionIcon color={copied ? 'teal' : 'gray'} variant="subtle" onClick={copy}>
                  {copied ? <Check size={16} /> : <Copy size={16} />}
                </ActionIcon>
              </Tooltip>
            )}
          </CopyButton>
        </Group>
        <Text size="sm" c="dimmed" mb="md">
          If you are using an AI agent (like Cursor, GitHub Copilot, or Antigravity) to build your project, 
          copy the markdown below and provide it to your agent as system context. This skill ensures your agent 
          structures your project correctly for this specific scheduler.
        </Text>
        <Code block style={{ whiteSpace: 'pre-wrap', maxHeight: 400, overflowY: 'auto' }}>
          {agentSkillMarkdown}
        </Code>
      </Paper>
    </Stack>
  );
}
