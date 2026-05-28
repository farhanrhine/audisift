/**
 * Global Feedback & Issue Ingestion Script
 * Injects a floating action button (FAB) that opens a beautiful glassmorphism modal
 * to report bugs or submit feedback to the system owner.
 */

(function () {
  // Prevent duplicate initialization
  if (window.__feedback_initialized) return;
  window.__feedback_initialized = true;

  // CSS Styles Injection
  const styles = `
    /* Floating Action Button (FAB) */
    .feedback-fab {
      position: fixed;
      bottom: 24px;
      right: 24px;
      z-index: 9999;
      background-color: var(--accent, #E52b50);
      color: #ffffff !important;
      border: 1px solid rgba(255, 255, 255, 0.1);
      border-radius: var(--radius-full, 9999px);
      padding: 10px 18px;
      font-family: var(--font-body), sans-serif;
      font-size: 0.88rem;
      font-weight: 600;
      box-shadow: 0 4px 14px rgba(229, 43, 80, 0.35);
      cursor: pointer;
      display: flex;
      align-items: center;
      gap: 8px;
      transition: all 0.3s cubic-bezier(0.25, 0.8, 0.25, 1);
      text-decoration: none;
    }
    .feedback-fab:hover {
      transform: translateY(-2px);
      box-shadow: 0 6px 20px rgba(229, 43, 80, 0.45);
      background-color: #d61e3f;
    }
    .feedback-fab svg {
      width: 18px;
      height: 18px;
      stroke: currentColor;
      stroke-width: 2.2;
      fill: none;
    }

    /* Modal Overlay */
    .feedback-overlay {
      position: fixed;
      inset: 0;
      background-color: rgba(26, 24, 22, 0.45);
      backdrop-filter: blur(4px);
      -webkit-backdrop-filter: blur(4px);
      z-index: 10000;
      display: flex;
      align-items: center;
      justify-content: center;
      opacity: 0;
      pointer-events: none;
      transition: opacity 0.3s cubic-bezier(0.25, 0.8, 0.25, 1);
      padding: 20px;
    }
    .feedback-overlay.open {
      opacity: 1;
      pointer-events: auto;
    }

    /* Modal Container */
    .feedback-modal {
      background-color: var(--paper-card, #ffffff);
      border: 1px solid var(--border, #dcdad2);
      border-radius: var(--radius-md, 12px);
      box-shadow: var(--shadow-hover, 0 15px 50px rgba(0, 0, 0, 0.08));
      width: 100%;
      max-width: 440px;
      padding: 28px;
      transform: translateY(20px) scale(0.95);
      transition: transform 0.3s cubic-bezier(0.25, 0.8, 0.25, 1);
      font-family: var(--font-body), sans-serif;
      color: var(--ink, #1a1816);
      position: relative;
    }
    .feedback-overlay.open .feedback-modal {
      transform: translateY(0) scale(1);
    }

    .feedback-modal-close {
      position: absolute;
      top: 20px;
      right: 20px;
      background: transparent;
      border: none;
      color: var(--ink-soft, #6b6357);
      cursor: pointer;
      display: flex;
      align-items: center;
      justify-content: center;
      width: 28px;
      height: 28px;
      border-radius: 50%;
      transition: var(--transition, all 0.2s);
    }
    .feedback-modal-close:hover {
      background-color: var(--paper-warm, #f2f0eb);
      color: var(--ink, #1a1816);
    }
    .feedback-modal-close svg {
      width: 16px;
      height: 16px;
      stroke: currentColor;
      stroke-width: 2;
      fill: none;
    }

    .feedback-modal h2 {
      font-family: var(--font-display), Georgia, serif;
      font-size: 1.6rem;
      font-weight: 500;
      margin-bottom: 6px;
      line-height: 1.2;
      color: var(--ink, #1a1816);
    }
    .feedback-modal p {
      font-size: 0.88rem;
      color: var(--ink-soft, #3d3a36);
      margin-bottom: 20px;
      line-height: 1.5;
    }

    .feedback-group {
      margin-bottom: 14px;
    }
    .feedback-group label {
      display: block;
      font-size: 0.72rem;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      color: var(--ink-muted, #6b6357);
      margin-bottom: 6px;
    }
    .feedback-group input,
    .feedback-group select,
    .feedback-group textarea {
      width: 100%;
      background: var(--paper-card, #ffffff);
      border: 1.5px solid var(--border, #dcdad2);
      border-radius: var(--radius-sm, 6px);
      padding: 10px 12px;
      color: var(--ink, #1a1816);
      font-family: var(--font-body), sans-serif;
      font-size: 0.9rem;
      outline: none;
      transition: all 0.2s;
    }
    .feedback-group input:focus,
    .feedback-group select:focus,
    .feedback-group textarea:focus {
      border-color: var(--accent, #E52b50);
      box-shadow: 0 0 0 3px var(--accent-light, rgba(229, 43, 80, 0.15));
    }
    .feedback-group textarea {
      resize: vertical;
      min-height: 100px;
    }

    .feedback-actions {
      display: flex;
      justify-content: flex-end;
      gap: 12px;
      margin-top: 20px;
    }
    .feedback-actions .btn {
      padding: 10px 18px;
      font-size: 0.88rem;
      font-weight: 600;
    }

    .feedback-msg {
      padding: 10px 14px;
      border-radius: var(--radius-sm, 6px);
      font-size: 0.88rem;
      margin-bottom: 16px;
      display: none;
      line-height: 1.4;
    }
    .feedback-msg.error {
      display: block;
      background-color: var(--danger-light, #fdecea);
      color: var(--danger, #c0392b);
      border: 1px solid rgba(192, 57, 43, 0.2);
    }
    .feedback-msg.success {
      display: block;
      background-color: rgba(43, 122, 80, 0.1);
      color: var(--accent-green, #2B7A50);
      border: 1px solid rgba(43, 122, 80, 0.2);
    }
  `;

  // Inject styles to head
  const styleEl = document.createElement('style');
  styleEl.textContent = styles;
  document.head.appendChild(styleEl);

  // Dynamic template elements creation
  const overlay = document.createElement('div');
  overlay.className = 'feedback-overlay';
  overlay.id = 'feedback-modal-overlay';

  overlay.innerHTML = `
    <div class="feedback-modal">
      <button class="feedback-modal-close" id="feedback-close-btn" title="Close">
        <svg viewBox="0 0 24 24"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>
      </button>
      <h2>Report an Issue</h2>
      <p>Spotted a bug, ran into an error, or have feature feedback? Let us know below.</p>
      
      <div id="feedback-status-msg" class="feedback-msg"></div>

      <form id="feedback-form">
        <div class="feedback-group">
          <label for="feedback-name">Your Name</label>
          <input type="text" id="feedback-name" placeholder="John Doe" />
        </div>
        <div class="feedback-group">
          <label for="feedback-email">Your Email</label>
          <input type="email" id="feedback-email" placeholder="john@example.com" required />
        </div>
        <div class="feedback-group">
          <label for="feedback-role">Role</label>
          <select id="feedback-role" required>
            <option value="candidate">Candidate</option>
            <option value="recruiter">Recruiter</option>
          </select>
        </div>
        <div class="feedback-group">
          <label for="feedback-desc">Describe the issue or feedback</label>
          <textarea id="feedback-desc" placeholder="Describe what went wrong or your feedback here..." required></textarea>
        </div>
        
        <div class="feedback-actions">
          <button type="button" class="btn btn-ghost" id="feedback-cancel-btn">Cancel</button>
          <button type="submit" class="btn btn-primary" id="feedback-submit-btn">Submit Report</button>
        </div>
      </form>
    </div>
  `;

  const fab = document.createElement('button');
  fab.className = 'feedback-fab';
  fab.id = 'feedback-fab-btn';
  fab.innerHTML = `
    <svg viewBox="0 0 24 24"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path></svg>
    Report Issue
  `;

  // Append to body after DOM is fully loaded or immediately if already loaded
  function initDOM() {
    document.body.appendChild(fab);
    document.body.appendChild(overlay);

    const form = document.getElementById('feedback-form');
    const closeBtn = document.getElementById('feedback-close-btn');
    const cancelBtn = document.getElementById('feedback-cancel-btn');
    const statusMsg = document.getElementById('feedback-status-msg');
    const nameInput = document.getElementById('feedback-name');
    const emailInput = document.getElementById('feedback-email');
    const roleSelect = document.getElementById('feedback-role');
    const descInput = document.getElementById('feedback-desc');

    // Show modal on FAB click
    fab.addEventListener('click', async () => {
      // Clear previous inputs
      statusMsg.style.display = 'none';
      descInput.value = '';
      
      // Auto-prefill if logged in
      const userInfo = await getFeedbackUserInfo();
      if (userInfo) {
        nameInput.value = userInfo.full_name || '';
        emailInput.value = userInfo.email || '';
        
        if (userInfo.role) {
          roleSelect.value = userInfo.role;
        } else if (userInfo.is_superuser) {
          roleSelect.value = 'recruiter';
        }
      }

      overlay.classList.add('open');
      descInput.focus();
    });

    // Close handlers
    function closeModal() {
      overlay.classList.remove('open');
    }

    closeBtn.addEventListener('click', closeModal);
    cancelBtn.addEventListener('click', closeModal);
    overlay.addEventListener('click', (e) => {
      if (e.target === overlay) closeModal();
    });

    // Form Submit
    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      
      const submitBtn = document.getElementById('feedback-submit-btn');
      const originalText = submitBtn.textContent;
      
      submitBtn.textContent = 'Submitting...';
      submitBtn.disabled = true;
      statusMsg.style.display = 'none';

      try {
        const payload = {
          reporter_name: nameInput.value.trim() || null,
          reporter_email: emailInput.value.trim(),
          role: roleSelect.value,
          description: descInput.value.trim()
        };

        const res = await fetch('/api/feedback/report', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json'
          },
          body: JSON.stringify(payload)
        });

        if (!res.ok) {
          const errData = await res.json().catch(() => ({}));
          throw new Error(errData.detail || 'Failed to submit report. Please try again.');
        }

        statusMsg.textContent = 'Thank you! Your feedback has been submitted successfully.';
        statusMsg.className = 'feedback-msg success';
        statusMsg.style.display = 'block';
        
        form.reset();

        // Close after a brief delay
        setTimeout(() => {
          closeModal();
          statusMsg.style.display = 'none';
        }, 2000);

      } catch (err) {
        statusMsg.textContent = err.message;
        statusMsg.className = 'feedback-msg error';
        statusMsg.style.display = 'block';
      } finally {
        submitBtn.textContent = originalText;
        submitBtn.disabled = false;
      }
    });
  }

  async function getFeedbackUserInfo() {
    if (typeof window.getCurrentUser === 'function') {
      try {
        return await window.getCurrentUser();
      } catch (e) {
        // Fallback
      }
    }
    const token = localStorage.getItem('access_token');
    if (token) {
      try {
        const response = await fetch('/users/me', {
          headers: { 'Authorization': `Bearer ${token}` }
        });
        if (response.ok) {
          return await response.json();
        }
      } catch (e) {
        console.error('Error fetching user for feedback:', e);
      }
    }
    return null;
  }

  // Load implementation
  if (document.readyState === 'complete' || document.readyState === 'interactive') {
    initDOM();
  } else {
    document.addEventListener('DOMContentLoaded', initDOM);
  }
})();
