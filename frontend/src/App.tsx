import React, { useState, useEffect, useRef } from 'react';
import axios from 'axios';
import { 
  Play, 
  Square, 
  Download, 
  RefreshCw, 
  Sliders, 
  Users, 
  LogOut, 
  Terminal, 
  Database, 
  FileCode, 
  Trash2, 
  AlertCircle, 
  CheckCircle2, 
  Clock, 
  Lock, 
  Plus, 
  X, 
  ShieldAlert, 
  Layers
} from 'lucide-react';

const API_BASE_URL = 'http://localhost:8000';

// Axios instance with default configurations
const api = axios.create({
  baseURL: API_BASE_URL,
});

// Request interceptor to automatically add token
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('session_token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

function App() {
  // Navigation & Auth States
  const [view, setView] = useState<'login' | 'signup' | 'dashboard'>('login');
  const [user, setUser] = useState<{ id: string; username: string; email: string; role: string } | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  // Form States (Auth)
  const [loginUsername, setLoginUsername] = useState('');
  const [loginPassword, setLoginPassword] = useState('');
  const [registerUsername, setRegisterUsername] = useState('');
  const [registerEmail, setRegisterEmail] = useState('');
  const [registerFullName, setRegisterFullName] = useState('');
  const [registerPassword, setRegisterPassword] = useState('');

  // Dashboard Sidebar/Tab Navigation
  const [activeSidebarTab, setActiveSidebarTab] = useState<'jobs' | 'admin'>('jobs');
  
  // Job Submission States
  const [submitType, setSubmitType] = useState<'file' | 'github'>('file');
  const [jobTitle, setJobTitle] = useState('');
  const [jobDescription, setJobDescription] = useState('');
  const [gpuCount, setGpuCount] = useState(1);
  const [cpuCores, setCpuCores] = useState('');
  const [memoryMb, setMemoryMb] = useState('');
  const [maxRuntime, setMaxRuntime] = useState('');
  const [queueName, setQueueName] = useState('default');
  const [priority, setPriority] = useState(5); // Ignored on submit if not admin
  const [envVars, setEnvVars] = useState<Array<{ key: string; value: string; isSecret: boolean }>>([]);
  const [uploadFile, setUploadFile] = useState<File | null>(null);

  // GitHub Job States
  const [repoUrl, setRepoUrl] = useState('');
  const [repoBranch, setRepoBranch] = useState('main');
  const [commitHash, setCommitHash] = useState('');
  const [repoSubdir, setRepoSubdir] = useState('');
  const [entrypoint, setEntrypoint] = useState('');

  // Lists & Data States
  const [jobs, setJobs] = useState<any[]>([]);
  const [adminJobs, setAdminJobs] = useState<any[]>([]);
  const [adminUsers, setAdminUsers] = useState<any[]>([]);
  const [isSubmitLoading, setIsSubmitLoading] = useState(false);

  // Selected Job Details Drawer States
  const [selectedJob, setSelectedJob] = useState<any | null>(null);
  const [selectedJobEvents, setSelectedJobEvents] = useState<any[]>([]);
  const [selectedJobArtifacts, setSelectedJobArtifacts] = useState<any[]>([]);
  const [selectedJobLogs, setSelectedJobLogs] = useState<string>('');
  const [logType, setLogType] = useState<'stdout' | 'stderr' | 'combined'>('stdout');
  const [isTrayOpen, setIsTrayOpen] = useState(false);
  
  // Polling intervals refs
  const pollIntervalRef = useRef<any>(null);
  const logPollIntervalRef = useRef<any>(null);

  // Read auth credentials on mount
  useEffect(() => {
    const savedToken = localStorage.getItem('session_token');
    const savedUser = localStorage.getItem('user_info');
    if (savedToken && savedUser) {
      const parsedUser = JSON.parse(savedUser);
      setUser(parsedUser);
      setView('dashboard');
    }
  }, []);

  // Poll for job updates and logs when dashboard is open
  useEffect(() => {
    if (view === 'dashboard') {
      fetchJobs();
      if (user?.role === 'admin' && activeSidebarTab === 'admin') {
        fetchAdminJobs();
        fetchAdminUsers();
      }
      
      pollIntervalRef.current = setInterval(() => {
        fetchJobs();
        if (user?.role === 'admin' && activeSidebarTab === 'admin') {
          fetchAdminJobs();
        }
      }, 5000);
    }

    return () => {
      if (pollIntervalRef.current) clearInterval(pollIntervalRef.current);
    };
  }, [view, activeSidebarTab, user]);

  // Poll logs for the currently selected job if it is running
  useEffect(() => {
    if (isTrayOpen && selectedJob) {
      fetchJobDetails(selectedJob.id);
      
      // Stop previous interval if any
      if (logPollIntervalRef.current) clearInterval(logPollIntervalRef.current);

      const isFinished = ['completed', 'failed', 'cancelled'].includes(selectedJob.status);
      if (!isFinished) {
        logPollIntervalRef.current = setInterval(() => {
          if (selectedJob) {
            fetchJobDetails(selectedJob.id);
          }
        }, 3000);
      }
    }

    return () => {
      if (logPollIntervalRef.current) clearInterval(logPollIntervalRef.current);
    };
  }, [isTrayOpen, selectedJob?.id, selectedJob?.status, logType]);

  // Clear messages on transition
  const clearMessages = () => {
    setErrorMsg(null);
    setSuccessMsg(null);
  };

  // ── Auth Handlers ────────────────────────────────────────

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    clearMessages();
    try {
      const response = await api.post('/auth/login', {
        username: loginUsername,
        password: loginPassword,
      });
      const data = response.data;
      localStorage.setItem('session_token', data.session_token);
      localStorage.setItem('user_info', JSON.stringify({
        id: data.user_id,
        username: data.username,
        email: data.email,
        role: data.role,
      }));
      setUser({
        id: data.user_id,
        username: data.username,
        email: data.email,
        role: data.role,
      });
      setView('dashboard');
      setLoginPassword('');
    } catch (err: any) {
      setErrorMsg(err.response?.data?.detail || 'Failed to authenticate. Please check your credentials.');
    }
  };

  const handleRegister = async (e: React.FormEvent) => {
    e.preventDefault();
    clearMessages();
    try {
      await api.post('/auth/register', {
        username: registerUsername,
        email: registerEmail,
        full_name: registerFullName || null,
        password: registerPassword,
      });
      setSuccessMsg('Account registered successfully! You can now log in.');
      setView('login');
      // Clear sign-up forms
      setRegisterUsername('');
      setRegisterEmail('');
      setRegisterFullName('');
      setRegisterPassword('');
    } catch (err: any) {
      setErrorMsg(err.response?.data?.detail || 'Registration failed. Verify username/email uniqueness.');
    }
  };

  const handleLogout = async () => {
    clearMessages();
    try {
      await api.post('/auth/logout');
    } catch (err) {
      // Best-effort logout API call
    }
    localStorage.removeItem('session_token');
    localStorage.removeItem('user_info');
    setUser(null);
    setSelectedJob(null);
    setIsTrayOpen(false);
    setView('login');
  };

  // ── Data Loading Handlers ─────────────────────────────────

  const fetchJobs = async () => {
    try {
      const response = await api.get('/jobs', {
        params: { page: 1, page_size: 50 }
      });
      setJobs(response.data.jobs);
    } catch (err) {
      console.error('Failed to load user jobs', err);
    }
  };

  const fetchAdminJobs = async () => {
    try {
      const response = await api.get('/admin/jobs', {
        params: { page: 1, page_size: 50 }
      });
      setAdminJobs(response.data.jobs);
    } catch (err) {
      console.error('Failed to load admin global jobs', err);
    }
  };

  const fetchAdminUsers = async () => {
    try {
      const response = await api.get('/admin/users');
      setAdminUsers(response.data);
    } catch (err) {
      console.error('Failed to load admin users', err);
    }
  };

  const fetchJobDetails = async (jobId: string) => {
    try {
      // Fetch fresh events
      const eventsRes = await api.get(`/jobs/${jobId}/events`);
      setSelectedJobEvents(eventsRes.data);

      // Fetch fresh artifacts
      const artifactsRes = await api.get(`/jobs/${jobId}/artifacts`);
      setSelectedJobArtifacts(artifactsRes.data);

      // Fetch logs (if run exists)
      try {
        const logsRes = await api.get(`/jobs/${jobId}/logs/${logType}`);
        setSelectedJobLogs(logsRes.data);
      } catch (logErr) {
        setSelectedJobLogs('Logs not available or run has not generated console outputs yet.');
      }
    } catch (err) {
      console.error('Failed to load job details', err);
    }
  };

  // ── Job Management Actions ────────────────────────────────

  const addEnvVar = () => {
    setEnvVars([...envVars, { key: '', value: '', isSecret: false }]);
  };

  const updateEnvVar = (index: number, field: 'key' | 'value' | 'isSecret', value: any) => {
    const updated = [...envVars];
    if (field === 'isSecret') {
      updated[index].isSecret = value;
    } else {
      updated[index][field] = value;
    }
    setEnvVars(updated);
  };

  const removeEnvVar = (index: number) => {
    setEnvVars(envVars.filter((_, i) => i !== index));
  };

  const handleJobSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    clearMessages();
    setIsSubmitLoading(true);

    const formattedEnvVars = envVars
      .filter((ev) => ev.key.trim() !== '')
      .map((ev) => ({
        var_name: ev.key.trim(),
        var_value: ev.value.trim(),
        is_secret: ev.isSecret,
      }));

    try {
      if (submitType === 'file') {
        if (!uploadFile) {
          setErrorMsg('Please select a .py or .sh script to upload.');
          setIsSubmitLoading(false);
          return;
        }

        const metadata = {
          title: jobTitle || null,
          description: jobDescription || null,
          requested_gpu_count: gpuCount,
          requested_cpu_cores: cpuCores ? parseInt(cpuCores) : null,
          requested_memory_mb: memoryMb ? parseInt(memoryMb) : null,
          max_runtime_seconds: maxRuntime ? parseInt(maxRuntime) : null,
          priority: user?.role === 'admin' ? priority : 5,
          queue_name: queueName,
          env_vars: formattedEnvVars,
        };

        const formData = new FormData();
        formData.append('file', uploadFile);
        formData.append('metadata', JSON.stringify(metadata));

        await api.post('/jobs/python-file', formData, {
          headers: { 'Content-Type': 'multipart/form-data' },
        });
      } else {
        if (!repoUrl || !entrypoint) {
          setErrorMsg('GitHub repository URL and Entrypoint script path are required.');
          setIsSubmitLoading(false);
          return;
        }

        const payload = {
          repo_url: repoUrl,
          repo_branch: repoBranch,
          repo_commit_hash: commitHash || null,
          repo_subdir: repoSubdir || null,
          entrypoint: entrypoint,
          title: jobTitle || null,
          description: jobDescription || null,
          requested_gpu_count: gpuCount,
          requested_cpu_cores: cpuCores ? parseInt(cpuCores) : null,
          requested_memory_mb: memoryMb ? parseInt(memoryMb) : null,
          max_runtime_seconds: maxRuntime ? parseInt(maxRuntime) : null,
          priority: user?.role === 'admin' ? priority : 5,
          queue_name: queueName,
          env_vars: formattedEnvVars,
        };

        await api.post('/jobs/github', payload);
      }

      setSuccessMsg('Job successfully submitted to queue!');
      // Clear forms
      setJobTitle('');
      setJobDescription('');
      setGpuCount(1);
      setCpuCores('');
      setMemoryMb('');
      setMaxRuntime('');
      setQueueName('default');
      setPriority(5);
      setEnvVars([]);
      setUploadFile(null);
      setRepoUrl('');
      setEntrypoint('');
      setRepoSubdir('');
      setCommitHash('');
      
      fetchJobs();
    } catch (err: any) {
      setErrorMsg(err.response?.data?.detail || 'Failed to submit job.');
    } finally {
      setIsSubmitLoading(false);
    }
  };

  const handleCancelJob = async (jobId: string) => {
    if (!window.confirm('Are you sure you want to cancel this job run?')) return;
    try {
      await api.post(`/jobs/${jobId}/cancel`);
      setSuccessMsg('Job cancellation initiated.');
      fetchJobs();
      if (selectedJob && selectedJob.id === jobId) {
        setSelectedJob({ ...selectedJob, status: 'cancelled' });
      }
    } catch (err: any) {
      setErrorMsg(err.response?.data?.detail || 'Failed to cancel job.');
    }
  };

  const handleDownloadArtifact = async (artifactId: string, fileName: string) => {
    try {
      if (!selectedJob) return;
      const response = await api.get(`/jobs/${selectedJob.id}/artifacts/${artifactId}/download`, {
        responseType: 'blob',
      });
      const url = window.URL.createObjectURL(new Blob([response.data]));
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', fileName);
      document.body.appendChild(link);
      link.click();
      link.remove();
    } catch (err: any) {
      alert('Failed to download artifact. Make sure the file exists on the server.');
    }
  };

  // ── Admin Handlers ────────────────────────────────────────

  const handleUpdateUser = async (userId: string, updates: { role?: string; status?: string }) => {
    try {
      await api.patch(`/admin/users/${userId}`, updates);
      fetchAdminUsers();
      setSuccessMsg('User successfully updated.');
    } catch (err: any) {
      setErrorMsg(err.response?.data?.detail || 'Failed to update user.');
    }
  };

  const handleDeleteUser = async (userId: string, username: string) => {
    if (!window.confirm(`Are you absolutely sure you want to delete user ${username}?`)) return;
    try {
      await api.delete(`/admin/users/${userId}`);
      fetchAdminUsers();
      setSuccessMsg('User account purged.');
    } catch (err: any) {
      setErrorMsg(err.response?.data?.detail || 'Failed to delete user.');
    }
  };

  const handleAdminUpdateJob = async (jobId: string, updates: { priority?: number; status?: string }) => {
    try {
      await api.patch(`/admin/jobs/${jobId}`, updates);
      fetchAdminJobs();
      fetchJobs();
      setSuccessMsg('Job modified.');
    } catch (err: any) {
      setErrorMsg(err.response?.data?.detail || 'Failed to update job.');
    }
  };

  // Helper formatting values
  const formatTime = (isoString: string | null) => {
    if (!isoString) return '-';
    return new Date(isoString).toLocaleString();
  };

  // Render Functions
  if (view === 'login') {
    return (
      <div className="auth-page">
        <div className="auth-sidebar">
          <Database size={64} style={{ color: 'var(--accent-cyan)', marginBottom: 24 }} />
          <div className="auth-title">GPU Job Scheduler</div>
          <p className="auth-subtitle">
            Secure, containerized execution environment for cluster-scale deep learning pipelines.
          </p>
        </div>
        <div className="auth-content">
          <div className="auth-form-card">
            <h2 style={{ fontSize: 24, marginBottom: 8 }}>Sign In</h2>
            <p style={{ color: 'var(--text-secondary)', marginBottom: 24 }}>Enter your credentials to manage cluster runs.</p>
            
            {errorMsg && (
              <div className="badge badge-failed" style={{ width: '100%', borderRadius: 6, padding: '10px 14px', marginBottom: 20 }}>
                <AlertCircle size={16} /> {errorMsg}
              </div>
            )}
            {successMsg && (
              <div className="badge badge-completed" style={{ width: '100%', borderRadius: 6, padding: '10px 14px', marginBottom: 20 }}>
                <CheckCircle2 size={16} /> {successMsg}
              </div>
            )}

            <form onSubmit={handleLogin}>
              <div className="form-group">
                <label className="form-label">Username</label>
                <input 
                  type="text" 
                  className="form-input" 
                  value={loginUsername} 
                  onChange={(e) => setLoginUsername(e.target.value)} 
                  required 
                />
              </div>
              <div className="form-group" style={{ marginBottom: 24 }}>
                <label className="form-label">Password</label>
                <input 
                  type="password" 
                  className="form-input" 
                  value={loginPassword} 
                  onChange={(e) => setLoginPassword(e.target.value)} 
                  required 
                />
              </div>
              <button type="submit" className="btn btn-primary" style={{ width: '100%' }}>
                Log In
              </button>
            </form>
            <p style={{ textAlign: 'center', marginTop: 24, fontSize: 13, color: 'var(--text-secondary)' }}>
              Don't have an account?{' '}
              <a href="#signup" onClick={() => { setView('signup'); clearMessages(); }}>
                Register here
              </a>
            </p>
          </div>
        </div>
      </div>
    );
  }

  if (view === 'signup') {
    return (
      <div className="auth-page">
        <div className="auth-sidebar">
          <Layers size={64} style={{ color: 'var(--accent-purple)', marginBottom: 24 }} />
          <div className="auth-title">Create Account</div>
          <p className="auth-subtitle">
            Get immediate access to dedicated, security-hardened GPU sandboxes.
          </p>
        </div>
        <div className="auth-content">
          <div className="auth-form-card">
            <h2 style={{ fontSize: 24, marginBottom: 8 }}>Register Account</h2>
            <p style={{ color: 'var(--text-secondary)', marginBottom: 24 }}>Sign up to deploy standalone scripts or repository pipelines.</p>
            
            {errorMsg && (
              <div className="badge badge-failed" style={{ width: '100%', borderRadius: 6, padding: '10px 14px', marginBottom: 20 }}>
                <AlertCircle size={16} /> {errorMsg}
              </div>
            )}

            <form onSubmit={handleRegister}>
              <div className="form-group">
                <label className="form-label">Username</label>
                <input 
                  type="text" 
                  className="form-input" 
                  value={registerUsername} 
                  onChange={(e) => setRegisterUsername(e.target.value)} 
                  required 
                  minLength={3}
                />
              </div>
              <div className="form-group">
                <label className="form-label">Email Address</label>
                <input 
                  type="email" 
                  className="form-input" 
                  value={registerEmail} 
                  onChange={(e) => setRegisterEmail(e.target.value)} 
                  required 
                />
              </div>
              <div className="form-group">
                <label className="form-label">Full Name (Optional)</label>
                <input 
                  type="text" 
                  className="form-input" 
                  value={registerFullName} 
                  onChange={(e) => setRegisterFullName(e.target.value)} 
                />
              </div>
              <div className="form-group" style={{ marginBottom: 24 }}>
                <label className="form-label">Password</label>
                <input 
                  type="password" 
                  className="form-input" 
                  value={registerPassword} 
                  onChange={(e) => setRegisterPassword(e.target.value)} 
                  required 
                  minLength={8}
                />
              </div>
              <button type="submit" className="btn btn-primary" style={{ width: '100%' }}>
                Register Account
              </button>
            </form>
            <p style={{ textAlign: 'center', marginTop: 24, fontSize: 13, color: 'var(--text-secondary)' }}>
              Already registered?{' '}
              <a href="#login" onClick={() => { setView('login'); clearMessages(); }}>
                Sign in instead
              </a>
            </p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="app-container">
      {/* Sidebar Navigation */}
      <div className="sidebar">
        <div className="logo-container">
          <Database size={24} style={{ color: 'var(--accent-cyan)' }} />
          <span className="logo-text">GPU Scheduler</span>
        </div>
        
        <div className="sidebar-nav">
          <div 
            className={`nav-item ${activeSidebarTab === 'jobs' ? 'active' : ''}`}
            onClick={() => setActiveSidebarTab('jobs')}
          >
            <Terminal size={18} />
            <span>My Jobs</span>
          </div>
          
          {user?.role === 'admin' && (
            <div 
              className={`nav-item ${activeSidebarTab === 'admin' ? 'active' : ''}`}
              onClick={() => {
                setActiveSidebarTab('admin');
                fetchAdminJobs();
                fetchAdminUsers();
              }}
            >
              <Sliders size={18} />
              <span>Admin Panel</span>
            </div>
          )}
        </div>
        
        <div className="sidebar-footer">
          <div className="user-info">
            <span className="username">{user?.username}</span>
            <span className="user-role">{user?.role}</span>
          </div>
          <div className="nav-item" onClick={handleLogout} style={{ color: '#ef4444' }}>
            <LogOut size={18} />
            <span>Sign Out</span>
          </div>
        </div>
      </div>

      {/* Main Dash Panel */}
      <div className="main-content">
        {errorMsg && (
          <div className="badge badge-failed" style={{ width: '100%', borderRadius: 6, padding: '12px 16px', marginBottom: 20, justifyContent: 'flex-start' }}>
            <AlertCircle size={16} /> <span>{errorMsg}</span>
            <X size={14} style={{ marginLeft: 'auto', cursor: 'pointer' }} onClick={clearMessages} />
          </div>
        )}
        {successMsg && (
          <div className="badge badge-completed" style={{ width: '100%', borderRadius: 6, padding: '12px 16px', marginBottom: 20, justifyContent: 'flex-start' }}>
            <CheckCircle2 size={16} /> <span>{successMsg}</span>
            <X size={14} style={{ marginLeft: 'auto', cursor: 'pointer' }} onClick={clearMessages} />
          </div>
        )}

        {activeSidebarTab === 'jobs' && (
          <>
            {/* Submit Job Box */}
            <div className="card">
              <h3 className="card-title">
                <Play size={20} style={{ color: 'var(--accent-cyan)' }} /> Submit New Training Job
              </h3>
              
              <div className="tabs">
                <div 
                  className={`tab ${submitType === 'file' ? 'active' : ''}`}
                  onClick={() => setSubmitType('file')}
                >
                  <FileCode size={16} style={{ display: 'inline', marginRight: 6, verticalAlign: 'text-bottom' }} />
                  Python/Shell Script
                </div>
                <div 
                  className={`tab ${submitType === 'github' ? 'active' : ''}`}
                  onClick={() => setSubmitType('github')}
                >
                  <svg className="lucide lucide-github" xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ display: 'inline', marginRight: 6, verticalAlign: 'text-bottom' }}><path d="M15 22v-4a4.8 4.8 0 0 0-1-3.5c3 0 6-2 6-5.5.08-1.25-.27-2.48-1-3.5.28-1.15.28-2.35 0-3.5 0 0-1 0-3 1.5-2.64-.5-5.36-.5-8 0C6 2 5 2 5 2c-.3 1.15-.3 2.35 0 3.5A5.403 5.403 0 0 0 4 9c0 3.5 3 5.5 6 5.5-.39.49-.68 1.05-.85 1.65-.17.6-.22 1.23-.15 1.85v4"></path><path d="M9 18c-4.51 2-5-2-7-2"></path></svg>
                  GitHub Repository
                </div>
              </div>

              <form onSubmit={handleJobSubmit}>
                <div className="form-row">
                  <div className="form-group">
                    <label className="form-label">Job Title</label>
                    <input 
                      type="text" 
                      className="form-input" 
                      placeholder="e.g. ResNet50 Training" 
                      value={jobTitle} 
                      onChange={(e) => setJobTitle(e.target.value)} 
                    />
                  </div>
                  <div className="form-group">
                    <label className="form-label">Queue Name</label>
                    <input 
                      type="text" 
                      className="form-input" 
                      value={queueName} 
                      onChange={(e) => setQueueName(e.target.value)} 
                      required 
                    />
                  </div>
                </div>

                <div className="form-group">
                  <label className="form-label">Description</label>
                  <textarea 
                    className="form-textarea" 
                    placeholder="Enter runtime description..." 
                    value={jobDescription} 
                    onChange={(e) => setJobDescription(e.target.value)} 
                  />
                </div>

                {submitType === 'file' ? (
                  <div className="form-group">
                    <label className="form-label">Select Script File (.py or .sh)</label>
                    <input 
                      type="file" 
                      className="form-input" 
                      accept=".py,.sh" 
                      onChange={(e) => setUploadFile(e.target.files?.[0] || null)} 
                      required 
                    />
                  </div>
                ) : (
                  <>
                    <div className="form-row">
                      <div className="form-group" style={{ gridColumn: 'span 2' }}>
                        <label className="form-label">GitHub Repo HTTPS URL</label>
                        <input 
                          type="text" 
                          className="form-input" 
                          placeholder="https://github.com/username/project.git" 
                          value={repoUrl} 
                          onChange={(e) => setRepoUrl(e.target.value)} 
                          required 
                        />
                      </div>
                      <div className="form-group">
                        <label className="form-label">Branch</label>
                        <input 
                          type="text" 
                          className="form-input" 
                          placeholder="main" 
                          value={repoBranch} 
                          onChange={(e) => setRepoBranch(e.target.value)} 
                        />
                      </div>
                    </div>
                    <div className="form-row">
                      <div className="form-group">
                        <label className="form-label">Entrypoint Script</label>
                        <input 
                          type="text" 
                          className="form-input" 
                          placeholder="e.g. scripts/train.py" 
                          value={entrypoint} 
                          onChange={(e) => setEntrypoint(e.target.value)} 
                          required 
                        />
                      </div>
                      <div className="form-group">
                        <label className="form-label">Target Subdirectory (Optional)</label>
                        <input 
                          type="text" 
                          className="form-input" 
                          placeholder="e.g. src" 
                          value={repoSubdir} 
                          onChange={(e) => setRepoSubdir(e.target.value)} 
                        />
                      </div>
                      <div className="form-group">
                        <label className="form-label">Commit Hash (Optional)</label>
                        <input 
                          type="text" 
                          className="form-input" 
                          placeholder="Latest if blank" 
                          value={commitHash} 
                          onChange={(e) => setCommitHash(e.target.value)} 
                        />
                      </div>
                    </div>
                  </>
                )}

                {/* Resource requests */}
                <h4 style={{ margin: '20px 0 10px', fontSize: 13, textTransform: 'uppercase', color: 'var(--text-secondary)' }}>Resource Requirements</h4>
                <div className="form-row">
                  <div className="form-group">
                    <label className="form-label">GPUs Count</label>
                    <select className="form-select" value={gpuCount} onChange={(e) => setGpuCount(parseInt(e.target.value))}>
                      <option value={0}>0 (CPU Only)</option>
                      <option value={1}>1 GPU</option>
                      <option value={2}>2 GPUs</option>
                      <option value={4}>4 GPUs</option>
                    </select>
                  </div>
                  <div className="form-group">
                    <label className="form-label">CPU Cores (Limit)</label>
                    <input type="number" className="form-input" placeholder="Host defaults" value={cpuCores} onChange={(e) => setCpuCores(e.target.value)} />
                  </div>
                  <div className="form-group">
                    <label className="form-label">RAM Memory (MB)</label>
                    <input type="number" className="form-input" placeholder="Host defaults" value={memoryMb} onChange={(e) => setMemoryMb(e.target.value)} />
                  </div>
                  <div className="form-group">
                    <label className="form-label">Max Runtime (Sec)</label>
                    <input type="number" className="form-input" placeholder="No limit" value={maxRuntime} onChange={(e) => setMaxRuntime(e.target.value)} />
                  </div>
                </div>

                {user?.role === 'admin' && (
                  <div className="form-group">
                    <label className="form-label">Job Submission Priority (Admin Override)</label>
                    <div className="priority-slider-container">
                      <input 
                        type="range" 
                        min="1" 
                        max="10" 
                        className="priority-slider"
                        value={priority}
                        onChange={(e) => setPriority(parseInt(e.target.value))}
                      />
                      <span className="priority-value">{priority}</span>
                    </div>
                  </div>
                )}

                {/* Env Vars */}
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', margin: '20px 0 10px' }}>
                  <h4 style={{ margin: 0, fontSize: 13, textTransform: 'uppercase', color: 'var(--text-secondary)' }}>Environment Variables</h4>
                  <button type="button" className="btn btn-secondary btn-small" onClick={addEnvVar}>
                    <Plus size={14} /> Add Env Var
                  </button>
                </div>
                {envVars.map((ev, index) => (
                  <div key={index} className="env-row">
                    <input 
                      type="text" 
                      className="form-input" 
                      placeholder="VAR_NAME" 
                      value={ev.key} 
                      onChange={(e) => updateEnvVar(index, 'key', e.target.value)} 
                    />
                    <input 
                      type="text" 
                      className="form-input" 
                      placeholder="value" 
                      value={ev.value} 
                      onChange={(e) => updateEnvVar(index, 'value', e.target.value)} 
                    />
                    <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
                      <label style={{ fontSize: 11, color: 'var(--text-secondary)', display: 'flex', flexDirection: 'column', alignItems: 'center', cursor: 'pointer' }}>
                        <Lock size={12} style={{ color: ev.isSecret ? 'var(--accent-purple)' : 'var(--text-muted)' }} />
                        <input 
                          type="checkbox" 
                          style={{ display: 'none' }}
                          checked={ev.isSecret} 
                          onChange={(e) => updateEnvVar(index, 'isSecret', e.target.checked)} 
                        />
                      </label>
                      <button type="button" className="btn btn-danger btn-small" onClick={() => removeEnvVar(index)} style={{ padding: 6 }}>
                        <Trash2 size={14} />
                      </button>
                    </div>
                  </div>
                ))}

                <div style={{ marginTop: 24 }}>
                  <button type="submit" className="btn btn-primary" disabled={isSubmitLoading}>
                    {isSubmitLoading ? (
                      <>
                        <RefreshCw size={16} className="animate-spin" /> Submitting Job...
                      </>
                    ) : (
                      <>
                        <Play size={16} /> Submit Cluster Job
                      </>
                    )}
                  </button>
                </div>
              </form>
            </div>

            {/* Jobs Queue List */}
            <div className="card">
              <h3 className="card-title">
                <Clock size={20} style={{ color: 'var(--accent-cyan)' }} /> My Job Runs History
              </h3>
              
              <div className="table-container">
                <table className="table">
                  <thead>
                    <tr>
                      <th>Title</th>
                      <th>Status</th>
                      <th>GPUs</th>
                      <th>Queue</th>
                      <th>Priority</th>
                      <th>Submitted At</th>
                      <th>Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {jobs.length === 0 ? (
                      <tr>
                        <td colSpan={7} style={{ textAlign: 'center', color: 'var(--text-secondary)', padding: '24px 0' }}>
                          No jobs submitted yet. Use the submit form above to start a container run.
                        </td>
                      </tr>
                    ) : (
                      jobs.map((j) => (
                        <tr 
                          key={j.id} 
                          style={{ cursor: 'pointer' }}
                          onClick={() => {
                            setSelectedJob(j);
                            setIsTrayOpen(true);
                          }}
                        >
                          <td style={{ fontWeight: 600 }}>{j.title || `Job [${j.id.slice(0, 8)}]`}</td>
                          <td>
                            <span className={`badge badge-${j.status}`}>
                              {j.status}
                            </span>
                          </td>
                          <td style={{ fontFamily: 'var(--mono-font)' }}>{j.requested_gpu_count}</td>
                          <td>{j.queue_name}</td>
                          <td style={{ fontFamily: 'var(--mono-font)' }}>{j.priority}</td>
                          <td>{formatTime(j.submitted_at)}</td>
                          <td onClick={(e) => e.stopPropagation()}>
                            {['queued', 'scheduled', 'running'].includes(j.status) && (
                              <button 
                                className="btn btn-danger btn-small"
                                onClick={() => handleCancelJob(j.id)}
                              >
                                <Square size={12} /> Cancel
                              </button>
                            )}
                          </td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          </>
        )}

        {activeSidebarTab === 'admin' && user?.role === 'admin' && (
          <>
            {/* Admin User Management */}
            <div className="card">
              <h3 className="card-title">
                <Users size={20} style={{ color: 'var(--accent-purple)' }} /> User Directory & Access Management
              </h3>
              <div className="table-container">
                <table className="table">
                  <thead>
                    <tr>
                      <th>Username</th>
                      <th>Email</th>
                      <th>Role</th>
                      <th>Account Status</th>
                      <th>Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {adminUsers.map((u) => (
                      <tr key={u.id}>
                        <td style={{ fontWeight: 600 }}>{u.username}</td>
                        <td>{u.email}</td>
                        <td>
                          <select 
                            className="form-select" 
                            style={{ width: 'auto', padding: '4px 8px' }}
                            value={u.role}
                            onChange={(e) => handleUpdateUser(u.id, { role: e.target.value })}
                            disabled={u.id === user?.id} // Don't demote yourself
                          >
                            <option value="user">User</option>
                            <option value="admin">Admin</option>
                          </select>
                        </td>
                        <td>
                          <select 
                            className="form-select" 
                            style={{ width: 'auto', padding: '4px 8px' }}
                            value={u.status}
                            onChange={(e) => handleUpdateUser(u.id, { status: e.target.value })}
                            disabled={u.id === user?.id}
                          >
                            <option value="active">Active</option>
                            <option value="suspended">Suspended</option>
                          </select>
                        </td>
                        <td>
                          <button 
                            className="btn btn-danger btn-small"
                            onClick={() => handleDeleteUser(u.id, u.username)}
                            disabled={u.id === user?.id}
                          >
                            <Trash2 size={12} /> Delete Account
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            {/* Global Queue / Priority Override */}
            <div className="card">
              <h3 className="card-title">
                <ShieldAlert size={20} style={{ color: 'var(--accent-purple)' }} /> Global Cluster Scheduler Queue
              </h3>
              <div className="table-container">
                <table className="table">
                  <thead>
                    <tr>
                      <th>Job Info</th>
                      <th>Status</th>
                      <th>Current Priority</th>
                      <th>Priority Adjustment</th>
                      <th>Overriding Status</th>
                      <th>Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {adminJobs.length === 0 ? (
                      <tr>
                        <td colSpan={6} style={{ textAlign: 'center', padding: '20px 0', color: 'var(--text-secondary)' }}>
                          No jobs registered on the cluster database.
                        </td>
                      </tr>
                    ) : (
                      adminJobs.map((j) => (
                        <tr key={j.id}>
                          <td>
                            <div style={{ fontWeight: 600 }}>{j.title || `Job [${j.id.slice(0, 8)}]`}</div>
                            <div style={{ fontSize: 11, color: 'var(--text-secondary)' }}>Owner ID: {j.user_id}</div>
                          </td>
                          <td>
                            <span className={`badge badge-${j.status}`}>{j.status}</span>
                          </td>
                          <td style={{ fontFamily: 'var(--mono-font)', fontWeight: 700, textAlign: 'center' }}>
                            {j.priority}
                          </td>
                          <td>
                            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                              <input 
                                type="range" 
                                min="1" 
                                max="10" 
                                className="priority-slider" 
                                style={{ width: 100 }}
                                value={j.priority}
                                onChange={(e) => handleAdminUpdateJob(j.id, { priority: parseInt(e.target.value) })}
                              />
                            </div>
                          </td>
                          <td>
                            <select 
                              className="form-select" 
                              style={{ width: 'auto', padding: '4px 8px' }}
                              value={j.status}
                              onChange={(e) => handleAdminUpdateJob(j.id, { status: e.target.value })}
                            >
                              <option value="queued">Queued</option>
                              <option value="scheduled">Scheduled</option>
                              <option value="running">Running</option>
                              <option value="completed">Completed</option>
                              <option value="failed">Failed</option>
                              <option value="cancelled">Cancelled</option>
                            </select>
                          </td>
                          <td>
                            {['queued', 'scheduled', 'running'].includes(j.status) && (
                              <button 
                                className="btn btn-danger btn-small"
                                onClick={() => handleCancelJob(j.id)}
                              >
                                Terminate
                              </button>
                            )}
                          </td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          </>
        )}
      </div>

      {/* Selected Job Details Slide-Out Drawer Tray */}
      <div 
        className={`detail-tray-backdrop ${isTrayOpen ? 'open' : ''}`}
        onClick={() => setIsTrayOpen(false)}
      >
        <div 
          className={`detail-tray ${isTrayOpen ? 'open' : ''}`}
          onClick={(e) => e.stopPropagation()}
        >
          <div className="detail-tray-header">
            <div>
              <h3 style={{ margin: 0, fontSize: 16 }}>{selectedJob?.title || 'Job Overview'}</h3>
              <span style={{ fontSize: 11, fontFamily: 'var(--mono-font)', color: 'var(--text-secondary)' }}>ID: {selectedJob?.id}</span>
            </div>
            <button className="btn btn-secondary" style={{ padding: 6 }} onClick={() => setIsTrayOpen(false)}>
              <X size={16} />
            </button>
          </div>

          <div className="detail-tray-body">
            {selectedJob && (
              <>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginBottom: 24 }}>
                  <div>
                    <span style={{ display: 'block', fontSize: 11, color: 'var(--text-secondary)', textTransform: 'uppercase' }}>Status</span>
                    <span className={`badge badge-${selectedJob.status}`} style={{ marginTop: 4 }}>{selectedJob.status}</span>
                  </div>
                  <div>
                    <span style={{ display: 'block', fontSize: 11, color: 'var(--text-secondary)', textTransform: 'uppercase' }}>Priority</span>
                    <span style={{ display: 'block', fontWeight: 700, fontSize: 16, marginTop: 4, fontFamily: 'var(--mono-font)' }}>{selectedJob.priority}</span>
                  </div>
                  <div>
                    <span style={{ display: 'block', fontSize: 11, color: 'var(--text-secondary)', textTransform: 'uppercase' }}>Requested GPUs</span>
                    <span style={{ display: 'block', fontWeight: 600, marginTop: 4 }}>{selectedJob.requested_gpu_count} GPU(s)</span>
                  </div>
                  <div>
                    <span style={{ display: 'block', fontSize: 11, color: 'var(--text-secondary)', textTransform: 'uppercase' }}>Queue</span>
                    <span style={{ display: 'block', fontWeight: 600, marginTop: 4 }}>{selectedJob.queue_name}</span>
                  </div>
                  <div>
                    <span style={{ display: 'block', fontSize: 11, color: 'var(--text-secondary)', textTransform: 'uppercase' }}>Submitted At</span>
                    <span style={{ display: 'block', fontSize: 12, marginTop: 4, color: 'var(--text-primary)' }}>{formatTime(selectedJob.submitted_at)}</span>
                  </div>
                  <div>
                    <span style={{ display: 'block', fontSize: 11, color: 'var(--text-secondary)', textTransform: 'uppercase' }}>Execution Finished</span>
                    <span style={{ display: 'block', fontSize: 12, marginTop: 4, color: 'var(--text-primary)' }}>{formatTime(selectedJob.finished_at)}</span>
                  </div>
                </div>

                {/* Event Logs Timeline */}
                <h4 style={{ fontSize: 13, textTransform: 'uppercase', color: 'var(--text-secondary)', marginBottom: 10 }}>Lifecycle Milestones</h4>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginBottom: 24, padding: 12, backgroundColor: 'var(--bg-primary)', borderRadius: 6, border: '1px solid var(--border-color)' }}>
                  {selectedJobEvents.length === 0 ? (
                    <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>No scheduler trace events available.</div>
                  ) : (
                    selectedJobEvents.map((evt) => (
                      <div key={evt.id} style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12 }}>
                        <span style={{ color: 'var(--accent-cyan)' }}>• {evt.event_message || evt.event_type}</span>
                        <span style={{ fontFamily: 'var(--mono-font)', color: 'var(--text-muted)', fontSize: 10 }}>{new Date(evt.created_at).toLocaleTimeString()}</span>
                      </div>
                    ))
                  )}
                </div>

                {/* Console Log Terminal */}
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
                  <h4 style={{ margin: 0, fontSize: 13, textTransform: 'uppercase', color: 'var(--text-secondary)' }}>Container Console Logs</h4>
                  
                  {/* Log type tabs */}
                  <div style={{ display: 'flex', gap: 8 }}>
                    <button 
                      className={`btn btn-secondary btn-small ${logType === 'stdout' ? 'btn-primary' : ''}`}
                      style={{ padding: '2px 8px', fontSize: 10, color: logType === 'stdout' ? '#000' : 'var(--text-secondary)' }}
                      onClick={() => setLogType('stdout')}
                    >
                      STDOUT
                    </button>
                    <button 
                      className={`btn btn-secondary btn-small ${logType === 'stderr' ? 'btn-primary' : ''}`}
                      style={{ padding: '2px 8px', fontSize: 10, color: logType === 'stderr' ? '#000' : 'var(--text-secondary)' }}
                      onClick={() => setLogType('stderr')}
                    >
                      STDERR
                    </button>
                  </div>
                </div>

                <div className="terminal-window" style={{ marginBottom: 24 }}>
                  <div className="terminal-header">
                    <div className="terminal-dots">
                      <span className="terminal-dot red"></span>
                      <span className="terminal-dot yellow"></span>
                      <span className="terminal-dot green"></span>
                    </div>
                    <span className="terminal-title">docker logs -f {selectedJob.id.slice(0, 8)}</span>
                  </div>
                  <div className="terminal-body">
                    {selectedJobLogs}
                  </div>
                </div>

                {/* Output Artifacts list */}
                <h4 style={{ fontSize: 13, textTransform: 'uppercase', color: 'var(--text-secondary)', marginBottom: 10 }}>Output Artifacts</h4>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                  {selectedJobArtifacts.length === 0 ? (
                    <div style={{ padding: 12, border: '1px dashed var(--border-color)', borderRadius: 6, textAlign: 'center', color: 'var(--text-secondary)', fontSize: 12 }}>
                      No output artifacts found. Make sure scripts output files to `/outputs` and training completes.
                    </div>
                  ) : (
                    selectedJobArtifacts.map((art) => (
                      <div 
                        key={art.id}
                        style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '10px 14px', border: '1px solid var(--border-color)', borderRadius: 6, backgroundColor: 'var(--bg-primary)' }}
                      >
                        <div>
                          <div style={{ fontSize: 13, fontWeight: 600 }}>{art.file_name}</div>
                          <div style={{ fontSize: 10, color: 'var(--text-muted)' }}>Size: {(art.file_size_bytes / 1024).toFixed(2)} KB</div>
                        </div>
                        <button 
                          className="btn btn-secondary btn-small"
                          onClick={() => handleDownloadArtifact(art.id, art.file_name)}
                        >
                          <Download size={14} /> Download
                        </button>
                      </div>
                    ))
                  )}
                </div>

                {/* Actions inside tray */}
                {['queued', 'scheduled', 'running'].includes(selectedJob.status) && (
                  <div style={{ marginTop: 32, borderTop: '1px solid var(--border-color)', paddingTop: 20 }}>
                    <button 
                      className="btn btn-danger" 
                      style={{ width: '100%' }}
                      onClick={() => handleCancelJob(selectedJob.id)}
                    >
                      Cancel / Stop Job Execution
                    </button>
                  </div>
                )}
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

export default App;
