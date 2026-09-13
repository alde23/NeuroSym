/**
 * NEUROSYM CHATGPT-GRADE REACTIVE FRONTEND APPLICATION
 * Handles Server-Sent Events (SSE) streaming, multi-turn state, markdown parsing,
 * evidence drawer updates, and dynamic theme switching.
 */

class NeuroSymApp {
  constructor() {
    this.sessionId = this.getOrInitSessionId();
    this.isStreaming = false;
    this.currentTheme = localStorage.getItem('neurosym_theme') || 'horizon-dark';
    
    // DOM Elements
    this.chatFeed = document.getElementById('chat-feed');
    this.chatThread = document.getElementById('chat-thread');
    this.userInput = document.getElementById('user-input');
    this.sendBtn = document.getElementById('send-btn');
    this.newChatBtn = document.getElementById('new-chat-btn');
    this.sessionsList = document.getElementById('sessions-list');
    this.themeSelect = document.getElementById('theme-select');
    
    // Header & Drawer Elements
    this.statusPill = document.getElementById('header-status-pill');
    this.statusText = document.getElementById('header-status-text');
    this.topicText = document.getElementById('header-topic-text');
    this.evidenceDrawer = document.getElementById('evidence-drawer');
    this.toggleDrawerBtn = document.getElementById('toggle-drawer-btn');
    this.closeDrawerBtn = document.getElementById('close-drawer-btn');
    
    // Drawer Stats Elements
    this.drawerPartners = document.getElementById('drawer-partners');
    this.drawerDuration = document.getElementById('drawer-duration');
    this.drawerCountries = document.getElementById('drawer-countries');
    this.drawerScheme = document.getElementById('drawer-scheme');
    this.drawerBudget = document.getElementById('drawer-budget');
    this.drawerBudgetRank = document.getElementById('drawer-budget-rank');
    this.drawerRulesList = document.getElementById('drawer-rules-list');
    this.drawerOutlierBadge = document.getElementById('drawer-outlier-badge');
    this.drawerOutlierAlert = document.getElementById('drawer-outlier-alert');

    this.init();
  }

  init() {
    // 1. Setup Theme
    this.applyTheme(this.currentTheme);
    this.themeSelect.value = this.currentTheme;
    this.themeSelect.addEventListener('change', (e) => this.applyTheme(e.target.value));

    // 2. Setup Events
    this.userInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        this.handleSend();
      }
    });

    this.userInput.addEventListener('input', () => {
      this.userInput.style.height = 'auto';
      this.userInput.style.height = Math.min(this.userInput.scrollHeight, 160) + 'px';
    });

    this.sendBtn.addEventListener('click', () => this.handleSend());
    this.newChatBtn.addEventListener('click', () => this.startNewChat());

    // Drawer Toggles
    this.toggleDrawerBtn.addEventListener('click', () => {
      this.evidenceDrawer.classList.toggle('collapsed');
    });
    this.closeDrawerBtn.addEventListener('click', () => {
      this.evidenceDrawer.classList.add('collapsed');
    });

    // Quick Action Prompt Buttons
    document.querySelectorAll('.quick-prompt-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        const prompt = btn.getAttribute('data-prompt');
        this.userInput.value = prompt;
        this.handleSend();
      });
    });

    // Load Sessions Sidebar and restore active session if available
    this.loadSessions(true);
  }

  getOrInitSessionId() {
    let sid = localStorage.getItem('neurosym_session_id');
    if (!sid) {
      sid = 'session-' + Math.random().toString(36).substring(2, 10);
      localStorage.setItem('neurosym_session_id', sid);
    }
    return sid;
  }

  applyTheme(themeName) {
    this.currentTheme = themeName;
    document.documentElement.setAttribute('data-theme', themeName);
    localStorage.setItem('neurosym_theme', themeName);
  }

  renderWelcomeHero() {
    this.chatThread.innerHTML = `
      <div class="card-panel" style="text-align: center; padding: 32px 20px; margin-top: 20px;" id="welcome-hero">
        <h1 style="font-size: 22px; font-weight: 800; margin-bottom: 8px; background: var(--accent-gradient); -webkit-background-clip: text; -webkit-text-fill-color: transparent;">
          Horizon Europe Feasibility & Grant Advisor
        </h1>
        <p style="color: var(--text-muted); max-width: 580px; margin: 0 auto 18px auto; font-size: 14px;">
          Evaluate your consortium structure against official General Annex B rules, compare budgets with 23,451 live CORDIS projects, and optimize your RIA/IA/CSA proposals.
        </p>
        <div class="suggestion-chips-container" style="justify-content: center;">
          <button class="chip-btn quick-prompt-btn" data-prompt="We are forming a consortium of 6 partners across Norway, Sweden, Finland, and Estonia for a 42-month CCUS (carbon capture) demonstration pilot. We are requesting €28,500,000 in EC funding. Please evaluate our application.">
            🌍 CCUS €28.5M 6-Partner Demonstration Pilot
          </button>
          <button class="chip-btn quick-prompt-btn" data-prompt="What is the average and median budget for Horizon Europe projects in 2021?">
            📊 2021 CORDIS Empirical Grant Benchmarks
          </button>
          <button class="chip-btn quick-prompt-btn" data-prompt="What are the official General Annex B eligibility rules for Horizon Europe RIA?">
            📜 General Annex B Statutory Rules
          </button>
        </div>
      </div>
    `;

    // Re-attach quick prompt buttons
    this.chatThread.querySelectorAll('.quick-prompt-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        const prompt = btn.getAttribute('data-prompt');
        this.userInput.value = prompt;
        this.handleSend();
      });
    });
  }

  startNewChat() {
    this.sessionId = 'session-' + Math.random().toString(36).substring(2, 10);
    localStorage.setItem('neurosym_session_id', this.sessionId);
    
    // Clear Chat UI and show welcome hero
    this.renderWelcomeHero();
    this.updateStatusPill('FEASIBLE', 'Ready');
    this.resetDrawerToEmpty();
    this.loadSessions(false);
  }

  resetDrawerToEmpty() {
    this.drawerPartners.textContent = '-';
    this.drawerDuration.textContent = '-';
    this.drawerCountries.textContent = '-';
    this.drawerBudget.textContent = '-';
    this.drawerBudgetRank.textContent = '-';
    this.drawerRulesList.innerHTML = '<div style="font-size: 13px; color: var(--text-dim); padding: 8px 0;">Awaiting proposal inquiry...</div>';
    
    const outlierBadge = document.getElementById('drawer-outlier-badge');
    if (outlierBadge) outlierBadge.style.display = 'none';
    const outlierAlert = document.getElementById('drawer-outlier-alert');
    if (outlierAlert) outlierAlert.style.display = 'none';
    const userStatItem = document.getElementById('user-stat-bar-item');
    if (userStatItem) userStatItem.style.display = 'none';
  }

  async loadSessions(autoRestoreCurrent = false) {
    try {
      const res = await fetch('/api/sessions');
      if (!res.ok) return;
      const data = await res.json();
      
      this.sessionsList.innerHTML = '';
      const sessions = data.sessions || [];

      if (sessions.length === 0) {
        this.sessionsList.innerHTML = '<div style="font-size: 12px; color: var(--text-dim); padding: 10px 8px;">No past consultations yet.</div>';
        return;
      }

      sessions.forEach(sess => {
        const item = document.createElement('div');
        const isActive = sess.session_id === this.sessionId;
        item.className = 'session-item' + (isActive ? ' active' : '');
        item.setAttribute('data-session-id', sess.session_id);
        
        let badgeClass = 'feasible';
        let badgeLabel = 'FEAS';
        if (sess.verdict === 'INFEASIBLE') {
          badgeClass = 'infeasible';
          badgeLabel = 'INFEAS';
        } else if (sess.verdict === 'CONDITIONALLY FEASIBLE') {
          badgeClass = 'conditional';
          badgeLabel = 'COND';
        }

        const specsHtml = sess.specs_summary 
          ? `<div class="session-specs-summary">${sess.specs_summary}</div>` 
          : `<div class="session-specs-summary">${sess.topic || 'Horizon Europe'}</div>`;

        item.innerHTML = `
          <div style="flex: 1; min-width: 0;">
            <div style="display: flex; justify-content: space-between; align-items: center; gap: 6px;">
              <span class="session-title-text" title="${sess.title}">${sess.title}</span>
              <span class="session-badge ${badgeClass}">${badgeLabel}</span>
            </div>
            ${specsHtml}
          </div>
        `;

        item.addEventListener('click', (e) => {
          e.preventDefault();
          this.switchSession(sess.session_id);
        });
        this.sessionsList.appendChild(item);
      });

      // Auto-restore session on page load if existing session found
      if (autoRestoreCurrent) {
        const hasCurrentSession = sessions.some(s => s.session_id === this.sessionId);
        if (hasCurrentSession) {
          this.switchSession(this.sessionId);
        } else if (sessions.length > 0) {
          // Default to most recent session
          this.switchSession(sessions[0].session_id);
        }
      }
    } catch (e) {
      console.warn('Could not load sessions:', e);
    }
  }

  async switchSession(newSessionId) {
    if (!newSessionId) return;
    this.sessionId = newSessionId;
    localStorage.setItem('neurosym_session_id', newSessionId);
    
    // Update active highlight in sidebar immediately
    const allItems = this.sessionsList.querySelectorAll('.session-item');
    allItems.forEach(el => {
      if (el.getAttribute('data-session-id') === newSessionId) {
        el.classList.add('active');
      } else {
        el.classList.remove('active');
      }
    });

    try {
      const res = await fetch(`/api/chat/${encodeURIComponent(newSessionId)}`);
      if (!res.ok) {
        console.warn(`Could not load session ${newSessionId}: HTTP ${res.status}`);
        return;
      }
      const sessionData = await res.json();

      // Clear Chat Thread
      this.chatThread.innerHTML = '';

      if (!sessionData.messages || sessionData.messages.length === 0) {
        this.renderWelcomeHero();
      } else {
        sessionData.messages.forEach((msg, idx) => {
          const isLastAssistant = (msg.role === 'assistant' && idx === sessionData.messages.length - 1);
          const bubble = this.appendMessageBubble(msg.role, msg.content, false);
          if (isLastAssistant && msg.metadata && msg.metadata.suggested_followups) {
            this.appendFollowupChips(bubble.rowElem, msg.metadata.suggested_followups);
          }
        });
      }

      // Update drawer and header with context and evidence
      const ctx = sessionData.proposal_context || {};
      const evidence = sessionData.latest_evidence || {};
      
      this.updateDrawerEvidence(ctx, evidence);
      
      if (sessionData.latest_verdict) {
        this.updateStatusPill(sessionData.latest_verdict);
      } else {
        this.updateStatusPill('FEASIBLE', 'Ready');
      }

      this.scrollToBottom();
    } catch (e) {
      console.error('Error switching session:', e);
    }
  }

  async handleSend() {
    const text = this.userInput.value.trim();
    if (!text || this.isStreaming) return;

    // Remove welcome hero if present
    const hero = document.getElementById('welcome-hero');
    if (hero) hero.remove();

    // Append user message
    this.appendMessageBubble('user', text, true);
    this.userInput.value = '';
    this.userInput.style.height = 'auto';

    // Prepare assistant streaming placeholder
    const assistantBubble = this.createAssistantStreamingBubble();
    this.isStreaming = true;
    this.sendBtn.disabled = true;

    try {
      const response = await fetch('/api/chat/stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: text,
          session_id: this.sessionId
        })
      });

      if (!response.ok) throw new Error('Stream request failed');

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let accumulatedText = '';

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;

        const chunkStr = decoder.decode(value, { stream: true });
        const lines = chunkStr.split('\n');

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            const rawJson = line.substring(6).trim();
            if (!rawJson) continue;

            try {
              const event = JSON.parse(rawJson);
              if (event.type === 'chunk') {
                accumulatedText += event.delta;
                assistantBubble.contentElem.innerHTML = this.renderMarkdown(accumulatedText) + '<span class="streaming-cursor"></span>';
                this.scrollToBottom();
              } else if (event.type === 'complete') {
                const finalData = event.data;
                assistantBubble.contentElem.innerHTML = this.renderMarkdown(finalData.reply);
                
                // Update Feasibility Header & Drawer
                this.updateStatusPill(finalData.verdict);
                this.updateDrawerEvidence(finalData.proposal_context, finalData);
                this.appendFollowupChips(assistantBubble.rowElem, finalData.suggested_followups);
              }
            } catch (err) {
              console.warn('Error parsing SSE line:', line, err);
            }
          }
        }
      }

    } catch (err) {
      assistantBubble.contentElem.innerHTML = `<p style="color: var(--verdict-infeasible);">Connection error: ${err.message}</p>`;
    } finally {
      this.isStreaming = false;
      this.sendBtn.disabled = false;
      this.loadSessions();
      this.scrollToBottom();
    }
  }

  createAssistantStreamingBubble() {
    const row = document.createElement('div');
    row.className = 'message-row assistant';
    
    const avatar = document.createElement('div');
    avatar.className = 'message-avatar';
    avatar.textContent = 'NS';

    const bubble = document.createElement('div');
    bubble.className = 'message-bubble';
    
    const content = document.createElement('div');
    content.innerHTML = '<span class="streaming-cursor"></span>';

    bubble.appendChild(content);
    row.appendChild(avatar);
    row.appendChild(bubble);
    this.chatThread.appendChild(row);
    this.scrollToBottom();

    return { rowElem: row, contentElem: content };
  }

  appendMessageBubble(role, content, animate = true) {
    const row = document.createElement('div');
    row.className = `message-row ${role}`;
    if (!animate) row.style.animation = 'none';

    const avatar = document.createElement('div');
    avatar.className = 'message-avatar';
    avatar.textContent = role === 'user' ? 'U' : 'NS';

    const bubble = document.createElement('div');
    bubble.className = 'message-bubble';
    bubble.innerHTML = this.renderMarkdown(content);

    if (role === 'user') {
      row.appendChild(bubble);
      row.appendChild(avatar);
    } else {
      row.appendChild(avatar);
      row.appendChild(bubble);
    }

    this.chatThread.appendChild(row);
    this.scrollToBottom();

    return { rowElem: row, bubbleElem: bubble };
  }

  appendFollowupChips(rowElem, chips) {
    if (!rowElem || !chips || chips.length === 0) return;
    
    // Remove existing chips container if any
    const existing = rowElem.querySelector('.suggestion-chips-container');
    if (existing) existing.remove();

    const container = document.createElement('div');
    container.className = 'suggestion-chips-container';
    
    chips.forEach(chipText => {
      const btn = document.createElement('button');
      btn.className = 'chip-btn';
      btn.textContent = '💡 ' + chipText;
      btn.addEventListener('click', () => {
        this.userInput.value = chipText;
        this.handleSend();
      });
      container.appendChild(btn);
    });

    const bubble = rowElem.querySelector('.message-bubble');
    if (bubble) {
      bubble.appendChild(container);
    } else {
      rowElem.appendChild(container);
    }
  }

  updateStatusPill(verdict, overrideLabel = null) {
    const label = overrideLabel || verdict;
    this.statusText.textContent = label;
    this.statusPill.className = 'status-pill';

    if (verdict === 'FEASIBLE') this.statusPill.classList.add('feasible');
    else if (verdict === 'INFEASIBLE') this.statusPill.classList.add('infeasible');
    else if (verdict === 'CONDITIONALLY FEASIBLE') this.statusPill.classList.add('conditional');
    else this.statusPill.classList.add('out-of-domain');
  }

  updateDrawerEvidence(ctx, data) {
    let requestedBudget = null;
    if (ctx) {
      const pCount = ctx.partner_count ? `${ctx.partner_count} partners` : '-';
      const pBreakdown = (ctx.member_state_count || ctx.associated_country_count) 
        ? ` (${ctx.member_state_count || 0} EU27, ${ctx.associated_country_count || 0} Assoc${ctx.third_country_count ? `, ${ctx.third_country_count} Third` : ''})` 
        : '';
      this.drawerPartners.textContent = pCount + pBreakdown;
      this.drawerDuration.textContent = ctx.requested_duration_months ? `${ctx.requested_duration_months} months` : '-';
      this.drawerCountries.textContent = ctx.countries && ctx.countries.length > 0 ? ctx.countries.join(', ') : '-';
      
      const scheme = ctx.funding_scheme || 'HORIZON-RIA';
      const schemeBadge = document.getElementById('drawer-scheme-badge');
      if (schemeBadge) schemeBadge.textContent = scheme;

      if (ctx.domain_topic) {
        this.topicText.textContent = `Topic: ${ctx.domain_topic}`;
      }
      
      if (ctx.requested_budget_eur) {
        requestedBudget = ctx.requested_budget_eur;
        this.drawerBudget.textContent = `€${(requestedBudget / 1e6).toFixed(2)}M (€${requestedBudget.toLocaleString()})`;
      } else {
        this.drawerBudget.textContent = '-';
      }
    }

    const ruleItems = [];
    if (data && Array.isArray(data.rule_evaluations) && data.rule_evaluations.length > 0) {
      data.rule_evaluations.forEach(r => {
        const isViolation = (r.status === 'FAILED' && (r.severity === 'error' || r.severity === 'ERROR'));
        const isCaution = (r.status === 'FAILED' && (r.severity === 'warning' || r.severity === 'WARNING'));
        const icon = isViolation ? '❌' : (isCaution ? '⚠️' : '✅');
        const statusBadge = isViolation 
          ? '<span class="session-badge infeasible">VIOLATION</span>' 
          : (isCaution ? '<span class="session-badge conditional">CAUTION</span>' : '<span class="session-badge feasible">PASSED</span>');
        const itemClass = isViolation ? 'rule-item violation' : (isCaution ? 'rule-item caution' : 'rule-item');
        
        ruleItems.push(`
          <div class="${itemClass}">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
              <span style="font-weight: 700; font-size: 12px; color: var(--text-main);">${icon} ${r.rule_id} (${r.name})</span>
              ${statusBadge}
            </div>
            <div style="font-size: 12.5px; color: var(--text-muted); line-height: 1.4;">${r.message || r.name}</div>
          </div>
        `);
      });
    } else if (data && Array.isArray(data.regulatory_evidence) && data.regulatory_evidence.length > 0) {
      data.regulatory_evidence.forEach(ruleStr => {
        const isViolation = ruleStr.includes('[VIOLATION]');
        const isCaution = ruleStr.includes('[CAUTION]');
        const icon = isViolation ? '❌' : (isCaution ? '⚠️' : '✅');
        const statusBadge = isViolation 
          ? '<span class="session-badge infeasible">VIOLATION</span>' 
          : (isCaution ? '<span class="session-badge conditional">CAUTION</span>' : '<span class="session-badge feasible">PASSED</span>');
        const itemClass = isViolation ? 'rule-item violation' : (isCaution ? 'rule-item caution' : 'rule-item');

        const cleanText = ruleStr
          .replace('[VIOLATION] ', '')
          .replace('[CAUTION] ', '')
          .replace('[COMPLIANT] ', '');

        const ruleIdMatch = cleanText.match(/^([A-Z0-9\-]+)\s*\(([^)]+)\):\s*(.*)$/);
        if (ruleIdMatch) {
          ruleItems.push(`
            <div class="${itemClass}">
              <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
                <span style="font-weight: 700; font-size: 12px; color: var(--text-main);">${icon} ${ruleIdMatch[1]} (${ruleIdMatch[2]})</span>
                ${statusBadge}
              </div>
              <div style="font-size: 12.5px; color: var(--text-muted); line-height: 1.4;">${ruleIdMatch[3]}</div>
            </div>
          `);
        } else {
          ruleItems.push(`
            <div class="${itemClass}">
              <div style="display: flex; justify-content: space-between; align-items: flex-start; gap: 8px;">
                <span style="font-size: 12.5px; color: var(--text-main); line-height: 1.4;">${icon} ${cleanText}</span>
                ${statusBadge}
              </div>
            </div>
          `);
        }
      });
    }

    if (ruleItems.length > 0) {
      this.drawerRulesList.innerHTML = ruleItems.join('');
    }

    if (data && data.domain_statistics) {
      const s = data.domain_statistics;
      if (s.budget_p5) document.getElementById('p5-val').textContent = `€${(s.budget_p5 / 1e6).toFixed(2)}M`;
      if (s.budget_p50) document.getElementById('p50-val').textContent = `€${(s.budget_p50 / 1e6).toFixed(2)}M`;
      if (s.budget_p95) document.getElementById('p95-val').textContent = `€${(s.budget_p95 / 1e6).toFixed(2)}M`;

      const cohortElem = document.getElementById('drawer-cohort-info');
      if (cohortElem) {
        cohortElem.textContent = `Benchmarked against ${s.comparable_project_count || 'live'} funded ${s.funding_scheme || 'HORIZON'} actions in CORDIS.`;
      }

      // Outlier detection and percentile ranking
      const outlierBadge = document.getElementById('drawer-outlier-badge');
      const outlierAlert = document.getElementById('drawer-outlier-alert');
      const userStatItem = document.getElementById('user-stat-bar-item');
      const userGrantVal = document.getElementById('user-grant-val');
      const userGrantFill = document.getElementById('user-grant-fill');

      if (requestedBudget && s.budget_p95) {
        const isOutlier = requestedBudget > s.budget_p95;
        const isLowOutlier = s.budget_p5 && requestedBudget < s.budget_p5;
        const rank = s.requested_budget_percentile !== null && s.requested_budget_percentile !== undefined 
          ? s.requested_budget_percentile 
          : (requestedBudget > s.budget_p95 ? 100.0 : 50.0);

        this.drawerBudgetRank.textContent = `${rank.toFixed(1)}th Percentile ${isOutlier ? '(Severe Outlier >P95)' : isLowOutlier ? '(Below P5)' : '(Normal Cohort Band)'}`;
        this.drawerBudgetRank.style.color = isOutlier ? 'var(--verdict-infeasible)' : isLowOutlier ? 'var(--verdict-conditional)' : 'var(--verdict-feasible)';

        if (outlierBadge) {
          outlierBadge.style.display = isOutlier ? 'inline-block' : 'none';
          outlierBadge.className = 'session-badge ' + (isOutlier ? 'infeasible' : 'feasible');
          outlierBadge.textContent = isOutlier ? '⚠️ OUTLIER (>P95)' : 'IN BAND';
        }

        if (outlierAlert) {
          outlierAlert.style.display = isOutlier ? 'block' : 'none';
          outlierAlert.innerHTML = `⚠️ <strong>Severe Outlier</strong>: Requested budget of <strong>€${(requestedBudget / 1e6).toFixed(2)}M</strong> is at the <strong>${rank.toFixed(1)}th percentile</strong>, exceeding historical 95th percentile benchmark (€${(s.budget_p95 / 1e6).toFixed(2)}M). Evaluators will scrutinize CAPEX and budget realism.`;
        }

        if (userStatItem && userGrantVal && userGrantFill) {
          userStatItem.style.display = 'flex';
          userGrantVal.textContent = `€${(requestedBudget / 1e6).toFixed(2)}M (${rank.toFixed(1)}th %ile)`;
          userGrantVal.style.color = isOutlier ? 'var(--verdict-infeasible)' : 'var(--accent-cyan)';
          userGrantFill.style.background = isOutlier ? 'var(--verdict-infeasible)' : 'var(--accent-cyan)';
        }
      } else {
        this.drawerBudgetRank.textContent = '-';
        if (outlierBadge) outlierBadge.style.display = 'none';
        if (outlierAlert) outlierAlert.style.display = 'none';
        if (userStatItem) userStatItem.style.display = 'none';
      }
    }
  }

  renderMarkdown(text) {
    if (!text) return '';
    
    // Clean XSS-safe markdown renderer supporting tables, code blocks, lists, quotes, and headers
    let html = text
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;') // Escape HTML
      .replace(/^### (.*$)/gim, '<h3 style="margin-top:14px; margin-bottom:6px; font-size:1.05rem; font-weight:700;">$1</h3>')
      .replace(/^## (.*$)/gim, '<h2 style="margin-top:16px; margin-bottom:8px; font-size:1.15rem; font-weight:700;">$1</h2>')
      .replace(/^# (.*$)/gim, '<h1 style="margin-top:18px; margin-bottom:10px; font-size:1.3rem; font-weight:800;">$1</h1>')
      .replace(/\*\*(.*?)\*\*/gim, '<strong>$1</strong>')
      .replace(/\*(.*?)\*/gim, '<em>$1</em>')
      .replace(/```([a-z]*)\n([\s\S]*?)```/gim, '<pre><code>$2</code></pre>')
      .replace(/```([\s\S]*?)```/gim, '<pre><code>$1</code></pre>')
      .replace(/`([^`]+)`/gim, '<code>$1</code>')
      .replace(/^\s*>\s+(.*$)/gim, '<blockquote>$1</blockquote>')
      .replace(/^\s*[-*•]\s+(.*$)/gim, '<li>$1</li>')
      .replace(/^\s*(\d+)\.\s+(.*$)/gim, '<li>$2</li>')
      .replace(/\n\n+/g, '</p><p>')
      .replace(/\n/g, '<br>');

    // Wrap list items cleanly
    html = html.replace(/(<li>.*?<\/li>)+/g, '<ul style="margin: 8px 0 10px 20px; padding: 0;">$&</ul>');
    return `<div class="md-content">${html}</div>`;
  }

  scrollToBottom(force = false) {
    const threshold = 120;
    const isNearBottom = this.chatFeed.scrollHeight - this.chatFeed.scrollTop - this.chatFeed.clientHeight < threshold;
    if (force || isNearBottom) {
      this.chatFeed.scrollTop = this.chatFeed.scrollHeight;
    }
  }
}

// Instantiate on DOM load
window.addEventListener('DOMContentLoaded', () => {
  window.neurosymApp = new NeuroSymApp();
});
