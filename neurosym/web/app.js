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
    this.drawerRulesList = document.getElementById('drawer-rules-list');

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

    // Load Sessions Sidebar
    this.loadSessions();
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

  startNewChat() {
    this.sessionId = 'session-' + Math.random().toString(36).substring(2, 10);
    localStorage.setItem('neurosym_session_id', this.sessionId);
    
    // Clear Chat UI
    this.chatThread.innerHTML = `
      <div class="card-panel" style="text-align: center; padding: 32px 20px; margin-top: 20px;" id="welcome-hero">
        <h1 style="font-size: 22px; font-weight: 800; margin-bottom: 8px; background: var(--accent-gradient); -webkit-background-clip: text; -webkit-text-fill-color: transparent;">
          Horizon Europe Feasibility & Grant Advisor
        </h1>
        <p style="color: var(--text-muted); max-width: 580px; margin: 0 auto 18px auto; font-size: 14px;">
          Evaluate your consortium structure against official General Annex B rules, compare budgets with 23,451 live CORDIS projects, and optimize your RIA/IA/CSA proposals.
        </p>
        <div class="suggestion-chips-container" style="justify-content: center;">
          <button class="chip-btn quick-prompt-btn" data-prompt="We are forming a consortium of 4 partners in Germany, Netherlands, and Sweden for a 36-month Horizon Europe RIA in autonomous robotics.">
            🤖 4-Partner AI Robotics RIA (36 Months)
          </button>
          <button class="chip-btn quick-prompt-btn" data-prompt="We are planning a 60-month Horizon Europe Research and Innovation Action with 2 partners in Germany.">
            ⚠️ Infeasible 2-Partner Proposal Test
          </button>
          <button class="chip-btn quick-prompt-btn" data-prompt="What is the average and 95th percentile budget for climate tech Horizon Europe projects?">
            📊 Climate Tech CORDIS Benchmarks
          </button>
        </div>
      </div>
    `;

    // Re-attach quick prompt buttons
    document.querySelectorAll('.quick-prompt-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        const prompt = btn.getAttribute('data-prompt');
        this.userInput.value = prompt;
        this.handleSend();
      });
    });

    this.updateStatusPill('FEASIBLE', 'Ready');
    this.loadSessions();
  }

  async loadSessions() {
    try {
      const res = await fetch('/api/sessions');
      if (!res.ok) return;
      const data = await res.json();
      
      this.sessionsList.innerHTML = '';
      data.sessions.forEach(sess => {
        const item = document.createElement('div');
        item.className = 'session-item' + (sess.session_id === this.sessionId ? ' active' : '');
        
        let badgeClass = 'feasible';
        if (sess.verdict === 'INFEASIBLE') badgeClass = 'infeasible';
        else if (sess.verdict === 'CONDITIONALLY FEASIBLE') badgeClass = 'conditional';

        item.innerHTML = `
          <span class="session-title-text" title="${sess.title}">${sess.title}</span>
          <span class="session-badge ${badgeClass}">${sess.verdict ? sess.verdict.substring(0, 4) : 'OK'}</span>
        `;

        item.addEventListener('click', () => this.switchSession(sess.session_id));
        this.sessionsList.appendChild(item);
      });
    } catch (e) {
      console.warn('Could not load sessions:', e);
    }
  }

  async switchSession(newSessionId) {
    this.sessionId = newSessionId;
    localStorage.setItem('neurosym_session_id', newSessionId);
    
    try {
      const res = await fetch(`/api/chat/${newSessionId}`);
      if (!res.ok) return;
      const sessionData = await res.json();

      this.chatThread.innerHTML = '';
      sessionData.messages.forEach(msg => {
        this.appendMessageBubble(msg.role, msg.content, false);
      });

      if (sessionData.proposal_context) {
        this.updateDrawerEvidence(sessionData.proposal_context, sessionData.latest_evidence);
      }
      if (sessionData.latest_verdict) {
        this.updateStatusPill(sessionData.latest_verdict);
      }

      this.loadSessions();
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
  }

  appendFollowupChips(rowElem, chips) {
    if (!chips || chips.length === 0) return;
    
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
    if (bubble) bubble.appendChild(container);
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
    if (ctx) {
      this.drawerPartners.textContent = ctx.partner_count ? `${ctx.partner_count} partners` : '-';
      this.drawerDuration.textContent = ctx.requested_duration_months ? `${ctx.requested_duration_months} mo` : '-';
      this.drawerCountries.textContent = ctx.countries && ctx.countries.length > 0 ? ctx.countries.join(', ') : '-';
      this.drawerScheme.textContent = ctx.funding_scheme || 'HORIZON-RIA';
      if (ctx.domain_topic) this.topicText.textContent = `Topic: ${ctx.domain_topic}`;
    }

    if (data && data.regulatory_evidence) {
      this.drawerRulesList.innerHTML = '';
      data.regulatory_evidence.forEach(ruleStr => {
        const item = document.createElement('div');
        item.className = 'rule-item';
        if (ruleStr.includes('[VIOLATION]')) item.classList.add('violation');
        else if (ruleStr.includes('[CAUTION]')) item.classList.add('caution');
        item.textContent = ruleStr;
        this.drawerRulesList.appendChild(item);
      });
    }

    if (data && data.domain_statistics) {
      const s = data.domain_statistics;
      if (s.budget_p5) document.getElementById('p5-val').textContent = `€${(s.budget_p5 / 1e6).toFixed(2)}M`;
      if (s.budget_p50) document.getElementById('p50-val').textContent = `€${(s.budget_p50 / 1e6).toFixed(2)}M`;
      if (s.budget_p95) document.getElementById('p95-val').textContent = `€${(s.budget_p95 / 1e6).toFixed(2)}M`;
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
