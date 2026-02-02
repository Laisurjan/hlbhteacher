/**
 * 教師員額控管系統 - 前端互動腳本
 *
 * 這個檔案負責處理：
 * 1. 登入/登出功能
 * 2. 會議展示模式切換
 * 3. 各種 UI 互動效果
 */

// ============================================================
// 登入/登出功能
// ============================================================

/**
 * 設定登入按鈕的點擊事件
 * 點擊後會顯示登入對話框
 */
function setupLoginButton() {
    const loginBtn = document.getElementById('login-btn');
    const loginModal = document.getElementById('login-modal');
    const loginSubmitBtn = document.getElementById('login-submit-btn');
    const loginCancelBtn = document.getElementById('login-cancel-btn');
    const passwordInput = document.getElementById('password-input');
    const loginError = document.getElementById('login-error');

    // 如果頁面沒有登入按鈕，就不執行
    if (!loginBtn) return;

    // 點擊登入按鈕，顯示對話框
    loginBtn.addEventListener('click', function() {
        loginModal.style.display = 'flex';
        passwordInput.value = '';
        loginError.style.display = 'none';
        passwordInput.focus();
    });

    // 點擊取消按鈕，關閉對話框
    loginCancelBtn.addEventListener('click', function() {
        loginModal.style.display = 'none';
    });

    // 點擊對話框外面，也關閉對話框
    loginModal.addEventListener('click', function(e) {
        if (e.target === loginModal) {
            loginModal.style.display = 'none';
        }
    });

    // 按 Enter 鍵也可以登入
    passwordInput.addEventListener('keypress', function(e) {
        if (e.key === 'Enter') {
            loginSubmitBtn.click();
        }
    });

    // 點擊登入提交按鈕
    loginSubmitBtn.addEventListener('click', async function() {
        const password = passwordInput.value;

        if (!password) {
            showLoginError('請輸入密碼');
            return;
        }

        try {
            // 送出登入請求到後端
            const response = await fetch('/api/login', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ password: password })
            });

            const result = await response.json();

            if (result.success) {
                // 登入成功，重新載入頁面
                window.location.reload();
            } else {
                // 登入失敗，顯示錯誤訊息
                showLoginError(result.message || '登入失敗');
            }
        } catch (error) {
            showLoginError('網路錯誤，請稍後再試');
        }
    });

    /**
     * 顯示登入錯誤訊息
     */
    function showLoginError(message) {
        loginError.textContent = message;
        loginError.style.display = 'block';
        passwordInput.focus();
        passwordInput.select();
    }
}

/**
 * 設定登出按鈕的點擊事件
 */
function setupLogoutButton() {
    const logoutBtn = document.getElementById('logout-btn');

    // 如果頁面沒有登出按鈕，就不執行
    if (!logoutBtn) return;

    logoutBtn.addEventListener('click', async function() {
        try {
            const response = await fetch('/api/logout', {
                method: 'POST'
            });

            const result = await response.json();

            if (result.success) {
                // 登出成功，重新載入頁面
                window.location.reload();
            }
        } catch (error) {
            alert('登出失敗，請稍後再試');
        }
    });
}

// ============================================================
// 會議展示模式
// ============================================================

/**
 * 設定會議展示模式按鈕
 * 點擊後會切換到大字體、簡化的展示模式
 */
function setupPresentationMode() {
    const presentationBtn = document.getElementById('presentation-mode-btn');

    // 如果頁面沒有展示模式按鈕，就不執行
    if (!presentationBtn) return;

    // 記錄目前是否在展示模式
    let isPresentationMode = false;

    presentationBtn.addEventListener('click', function() {
        isPresentationMode = !isPresentationMode;

        if (isPresentationMode) {
            // 進入展示模式
            document.body.classList.add('presentation-mode');
            presentationBtn.textContent = '退出展示模式';

            // 進入全螢幕（如果瀏覽器支援）
            if (document.documentElement.requestFullscreen) {
                document.documentElement.requestFullscreen();
            }
        } else {
            // 退出展示模式
            document.body.classList.remove('presentation-mode');
            presentationBtn.textContent = '會議展示模式';

            // 退出全螢幕
            if (document.exitFullscreen) {
                document.exitFullscreen();
            }
        }
    });

    // 監聽 ESC 鍵退出展示模式
    document.addEventListener('keydown', function(e) {
        if (e.key === 'Escape' && isPresentationMode) {
            isPresentationMode = false;
            document.body.classList.remove('presentation-mode');
            presentationBtn.textContent = '會議展示模式';
        }
    });
}

// ============================================================
// 工具函數
// ============================================================

/**
 * 格式化數字，加上千分位符號
 * 例如：1234567 -> 1,234,567
 */
function formatNumber(num) {
    return num.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ',');
}

/**
 * 顯示載入中的提示
 */
function showLoading(message = '載入中...') {
    // 建立載入提示元素
    const loading = document.createElement('div');
    loading.id = 'loading-overlay';
    loading.innerHTML = `
        <div class="loading-content">
            <div class="loading-spinner"></div>
            <p>${message}</p>
        </div>
    `;
    loading.style.cssText = `
        position: fixed;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        background: rgba(0, 0, 0, 0.5);
        display: flex;
        justify-content: center;
        align-items: center;
        z-index: 9999;
    `;

    // 加入到頁面
    document.body.appendChild(loading);
}

/**
 * 隱藏載入中的提示
 */
function hideLoading() {
    const loading = document.getElementById('loading-overlay');
    if (loading) {
        loading.remove();
    }
}

/**
 * 顯示提示訊息（類似 toast）
 */
function showToast(message, type = 'info') {
    // 建立提示元素
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.textContent = message;
    toast.style.cssText = `
        position: fixed;
        bottom: 20px;
        left: 50%;
        transform: translateX(-50%);
        padding: 12px 24px;
        border-radius: 8px;
        color: white;
        font-weight: 500;
        z-index: 9999;
        animation: slideUp 0.3s ease;
    `;

    // 根據類型設定背景色
    switch (type) {
        case 'success':
            toast.style.backgroundColor = '#16a34a';
            break;
        case 'error':
            toast.style.backgroundColor = '#dc2626';
            break;
        case 'warning':
            toast.style.backgroundColor = '#f59e0b';
            break;
        default:
            toast.style.backgroundColor = '#2563eb';
    }

    // 加入到頁面
    document.body.appendChild(toast);

    // 3 秒後自動消失
    setTimeout(() => {
        toast.style.animation = 'slideDown 0.3s ease';
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}

/**
 * 確認對話框（比 confirm 更好看）
 */
function showConfirm(message, onConfirm, onCancel) {
    const modal = document.createElement('div');
    modal.className = 'modal';
    modal.innerHTML = `
        <div class="modal-content">
            <p style="margin-bottom: 1rem;">${message}</p>
            <div class="modal-buttons">
                <button class="btn btn-primary" id="confirm-yes">確定</button>
                <button class="btn btn-secondary" id="confirm-no">取消</button>
            </div>
        </div>
    `;
    modal.style.display = 'flex';

    document.body.appendChild(modal);

    // 確定按鈕
    modal.querySelector('#confirm-yes').addEventListener('click', () => {
        modal.remove();
        if (onConfirm) onConfirm();
    });

    // 取消按鈕
    modal.querySelector('#confirm-no').addEventListener('click', () => {
        modal.remove();
        if (onCancel) onCancel();
    });
}

// ============================================================
// 資料 API 函數
// ============================================================

/**
 * 取得節數總覽資料
 */
async function fetchSummary() {
    try {
        const response = await fetch('/api/summary');
        return await response.json();
    } catch (error) {
        console.error('取得總覽資料失敗:', error);
        return null;
    }
}

/**
 * 取得教師資料
 */
async function fetchTeachers() {
    try {
        const response = await fetch('/api/teachers');
        return await response.json();
    } catch (error) {
        console.error('取得教師資料失敗:', error);
        return null;
    }
}

/**
 * 取得課程資料
 */
async function fetchCourses() {
    try {
        const response = await fetch('/api/courses');
        return await response.json();
    } catch (error) {
        console.error('取得課程資料失敗:', error);
        return null;
    }
}

/**
 * 更新教師資料
 */
async function updateTeachers(data) {
    try {
        const response = await fetch('/api/teachers', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(data)
        });
        return await response.json();
    } catch (error) {
        console.error('更新教師資料失敗:', error);
        return { success: false, message: '網路錯誤' };
    }
}

/**
 * 更新單一領域資料
 */
async function updateDomain(domainId, data) {
    try {
        const response = await fetch(`/api/domain/${domainId}`, {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(data)
        });
        return await response.json();
    } catch (error) {
        console.error('更新領域資料失敗:', error);
        return { success: false, message: '網路錯誤' };
    }
}

// ============================================================
// 頁面初始化
// ============================================================

/**
 * 當頁面載入完成時執行
 */
document.addEventListener('DOMContentLoaded', function() {
    // 設定登入/登出按鈕
    setupLoginButton();
    setupLogoutButton();

    // 設定展示模式按鈕
    setupPresentationMode();

    // 加入 CSS 動畫
    const style = document.createElement('style');
    style.textContent = `
        @keyframes slideUp {
            from {
                opacity: 0;
                transform: translateX(-50%) translateY(20px);
            }
            to {
                opacity: 1;
                transform: translateX(-50%) translateY(0);
            }
        }
        @keyframes slideDown {
            from {
                opacity: 1;
                transform: translateX(-50%) translateY(0);
            }
            to {
                opacity: 0;
                transform: translateX(-50%) translateY(20px);
            }
        }
        .loading-spinner {
            width: 40px;
            height: 40px;
            border: 4px solid #f3f3f3;
            border-top: 4px solid #2563eb;
            border-radius: 50%;
            animation: spin 1s linear infinite;
        }
        @keyframes spin {
            0% { transform: rotate(0deg); }
            100% { transform: rotate(360deg); }
        }
        .loading-content {
            text-align: center;
            color: white;
        }
        .loading-content p {
            margin-top: 1rem;
        }
    `;
    document.head.appendChild(style);
});

// ============================================================
// 匯出函數（讓其他腳本可以使用）
// ============================================================

// 這些函數可以在其他頁面的腳本中使用
window.TeacherQuotaSystem = {
    showLoading,
    hideLoading,
    showToast,
    showConfirm,
    formatNumber,
    fetchSummary,
    fetchTeachers,
    fetchCourses,
    updateTeachers,
    updateDomain
};
