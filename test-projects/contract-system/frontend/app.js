/**
 * 合同管理系统 - 主应用
 */

// ==================== 工具函数 ====================

function formatMoney(amount) {
    return new Intl.NumberFormat('zh-CN', { style: 'currency', currency: 'CNY' }).format(amount);
}

function formatDate(date) {
    if (!date) return '-';
    return date.split('T')[0];
}

function getStatusTag(status) {
    const statusMap = {
        // 客户状态
        active: { text: '活跃', class: 'tag-green' },
        inactive: { text: '停用', class: 'tag-gray' },
        // 信用等级
        normal: { text: '普通', class: 'tag-blue' },
        gold: { text: '黄金', class: 'tag-orange' },
        platinum: { text: '铂金', class: 'tag-green' },
        blacklist: { text: '黑名单', class: 'tag-red' },
        // 合同状态
        draft: { text: '草稿', class: 'tag-gray' },
        pending: { text: '待审批', class: 'tag-orange' },
        approved: { text: '已审批', class: 'tag-blue' },
        terminated: { text: '已终止', class: 'tag-red' },
        completed: { text: '已完成', class: 'tag-green' },
        // 付款状态
        paid: { text: '已付', class: 'tag-green' },
        overdue: { text: '逾期', class: 'tag-red' },
        cancelled: { text: '已取消', class: 'tag-gray' },
        // 发票状态
        sent: { text: '已发送', class: 'tag-blue' },
        void: { text: '作废', class: 'tag-gray' },
    };
    const info = statusMap[status] || { text: status, class: 'tag-gray' };
    return `<span class="tag ${info.class}">${info.text}</span>`;
}

// ==================== 页面渲染 ====================

let currentPage = 'dashboard';

function showPage(page) {
    currentPage = page;
    document.querySelectorAll('.menu-item').forEach(item => {
        item.classList.toggle('active', item.dataset.page === page);
    });

    const titles = {
        dashboard: '工作台',
        customers: '客户管理',
        contracts: '合同管理',
        payments: '付款管理',
        invoices: '发票管理',
    };
    document.getElementById('page-title').textContent = titles[page] || page;

    switch (page) {
        case 'dashboard': renderDashboard(); break;
        case 'customers': renderCustomers(); break;
        case 'contracts': renderContracts(); break;
        case 'payments': renderPayments(); break;
        case 'invoices': renderInvoices(); break;
    }
}

// ==================== 工作台 ====================

async function renderDashboard() {
    const stats = await api.dashboard.stats();
    const recent = await api.contracts.recent(5);

    document.getElementById('content').innerHTML = `
        <div class="stats-grid">
            <div class="stat-card">
                <div class="label">客户总数</div>
                <div class="value">${stats.total_customers}</div>
            </div>
            <div class="stat-card">
                <div class="label">合同总数</div>
                <div class="value">${stats.total_contracts}</div>
            </div>
            <div class="stat-card success">
                <div class="label">执行中合同</div>
                <div class="value">${stats.active_contracts}</div>
            </div>
            <div class="stat-card">
                <div class="label">合同总金额</div>
                <div class="value">${formatMoney(stats.total_amount)}</div>
            </div>
            <div class="stat-card warning">
                <div class="label">待收款项</div>
                <div class="value">${formatMoney(stats.pending_payments)}</div>
            </div>
            <div class="stat-card danger">
                <div class="label">逾期付款</div>
                <div class="value">${stats.overdue_payments}</div>
            </div>
        </div>

        <div class="card">
            <div class="card-header">
                <h3>最近合同</h3>
                <button class="btn btn-primary" onclick="showPage('contracts')">查看全部</button>
            </div>
            <div class="card-body">
                <div class="table-container">
                    <table>
                        <thead>
                            <tr>
                                <th>合同编号</th>
                                <th>合同标题</th>
                                <th>客户</th>
                                <th>金额</th>
                                <th>状态</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${recent.items.map(c => `
                                <tr onclick="showContractDetail(${c.id})" style="cursor: pointer;">
                                    <td>${c.contract_no}</td>
                                    <td>${c.title}</td>
                                    <td>${c.customer_name || '-'}</td>
                                    <td class="amount">${formatMoney(c.amount)}</td>
                                    <td>${getStatusTag(c.status)}</td>
                                </tr>
                            `).join('')}
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
    `;
}

// ==================== 客户管理 ====================

async function renderCustomers() {
    const data = await api.customers.list();

    document.getElementById('content').innerHTML = `
        <div class="card">
            <div class="card-header">
                <h3>客户列表</h3>
                <button class="btn btn-primary" onclick="showCustomerForm()">新增客户</button>
            </div>
            <div class="card-body">
                <div class="table-container">
                    <table>
                        <thead>
                            <tr>
                                <th>客户编码</th>
                                <th>客户名称</th>
                                <th>联系人</th>
                                <th>电话</th>
                                <th>信用等级</th>
                                <th>状态</th>
                                <th>操作</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${data.items.map(c => `
                                <tr>
                                    <td>${c.code}</td>
                                    <td>${c.name}</td>
                                    <td>${c.contact_person || '-'}</td>
                                    <td>${c.phone || '-'}</td>
                                    <td>${getStatusTag(c.credit_level)}</td>
                                    <td>${getStatusTag(c.status)}</td>
                                    <td>
                                        <button class="btn btn-link" onclick="showCustomerForm(${c.id})">编辑</button>
                                    </td>
                                </tr>
                            `).join('')}
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
    `;
}

async function showCustomerForm(id = null) {
    let customer = { name: '', code: '', contact_person: '', phone: '', email: '', address: '', credit_level: 'normal' };
    if (id) {
        customer = await api.customers.get(id);
    }

    document.getElementById('modal-title').textContent = id ? '编辑客户' : '新增客户';
    document.getElementById('modal-body').innerHTML = `
        <form id="customerForm">
            <div class="form-row">
                <div class="form-group">
                    <label>客户名称 *</label>
                    <input type="text" class="form-control" name="name" value="${customer.name}" required>
                </div>
                <div class="form-group">
                    <label>客户编码 *</label>
                    <input type="text" class="form-control" name="code" value="${customer.code}" required>
                </div>
            </div>
            <div class="form-row">
                <div class="form-group">
                    <label>联系人</label>
                    <input type="text" class="form-control" name="contact_person" value="${customer.contact_person || ''}">
                </div>
                <div class="form-group">
                    <label>电话</label>
                    <input type="text" class="form-control" name="phone" value="${customer.phone || ''}">
                </div>
            </div>
            <div class="form-group">
                <label>邮箱</label>
                <input type="email" class="form-control" name="email" value="${customer.email || ''}">
            </div>
            <div class="form-group">
                <label>地址</label>
                <input type="text" class="form-control" name="address" value="${customer.address || ''}">
            </div>
            <div class="form-group">
                <label>信用等级</label>
                <select class="form-control" name="credit_level">
                    <option value="normal" ${customer.credit_level === 'normal' ? 'selected' : ''}>普通</option>
                    <option value="gold" ${customer.credit_level === 'gold' ? 'selected' : ''}>黄金</option>
                    <option value="platinum" ${customer.credit_level === 'platinum' ? 'selected' : ''}>铂金</option>
                    <option value="blacklist" ${customer.credit_level === 'blacklist' ? 'selected' : ''}>黑名单</option>
                </select>
            </div>
            <div class="modal-footer">
                <button type="button" class="btn" onclick="closeModal()">取消</button>
                <button type="submit" class="btn btn-primary">保存</button>
            </div>
        </form>
    `;

    document.getElementById('customerForm').onsubmit = async (e) => {
        e.preventDefault();
        const formData = new FormData(e.target);
        const data = Object.fromEntries(formData);

        if (id) {
            await api.customers.update(id, data);
        } else {
            await api.customers.create(data);
        }
        closeModal();
        renderCustomers();
    };

    openModal();
}

// ==================== 合同管理 ====================

async function renderContracts() {
    const data = await api.contracts.list();

    document.getElementById('content').innerHTML = `
        <div class="card">
            <div class="card-header">
                <h3>合同列表</h3>
                <button class="btn btn-primary" onclick="showContractForm()">新增合同</button>
            </div>
            <div class="card-body">
                <div class="table-container">
                    <table>
                        <thead>
                            <tr>
                                <th>合同编号</th>
                                <th>合同标题</th>
                                <th>客户</th>
                                <th>金额</th>
                                <th>类型</th>
                                <th>状态</th>
                                <th>操作</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${data.items.map(c => `
                                <tr>
                                    <td>${c.contract_no}</td>
                                    <td>${c.title}</td>
                                    <td>${c.customer_name || '-'}</td>
                                    <td class="amount">${formatMoney(c.amount)}</td>
                                    <td>${c.type}</td>
                                    <td>${getStatusTag(c.status)}</td>
                                    <td>
                                        <button class="btn btn-link" onclick="showContractDetail(${c.id})">详情</button>
                                        <button class="btn btn-link" onclick="showContractForm(${c.id})">编辑</button>
                                    </td>
                                </tr>
                            `).join('')}
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
    `;
}

async function showContractForm(id = null) {
    let contract = { contract_no: '', title: '', customer_id: '', amount: '', type: 'sales', description: '', sign_date: '', start_date: '', end_date: '' };
    if (id) {
        contract = await api.contracts.get(id);
    }

    const customers = await api.customers.list();

    document.getElementById('modal-title').textContent = id ? '编辑合同' : '新增合同';
    document.getElementById('modal-body').innerHTML = `
        <form id="contractForm">
            <div class="form-row">
                <div class="form-group">
                    <label>合同编号 *</label>
                    <input type="text" class="form-control" name="contract_no" value="${contract.contract_no}" required>
                </div>
                <div class="form-group">
                    <label>合同标题 *</label>
                    <input type="text" class="form-control" name="title" value="${contract.title}" required>
                </div>
            </div>
            <div class="form-row">
                <div class="form-group">
                    <label>客户 *</label>
                    <select class="form-control" name="customer_id" required>
                        <option value="">请选择客户</option>
                        ${customers.items.map(c => `<option value="${c.id}" ${contract.customer_id == c.id ? 'selected' : ''}>${c.name}</option>`).join('')}
                    </select>
                </div>
                <div class="form-group">
                    <label>金额 *</label>
                    <input type="number" class="form-control" name="amount" value="${contract.amount}" step="0.01" required>
                </div>
            </div>
            <div class="form-row">
                <div class="form-group">
                    <label>合同类型</label>
                    <select class="form-control" name="type">
                        <option value="sales" ${contract.type === 'sales' ? 'selected' : ''}>销售合同</option>
                        <option value="purchase" ${contract.type === 'purchase' ? 'selected' : ''}>采购合同</option>
                        <option value="service" ${contract.type === 'service' ? 'selected' : ''}>服务合同</option>
                        <option value="framework" ${contract.type === 'framework' ? 'selected' : ''}>框架合同</option>
                    </select>
                </div>
                <div class="form-group">
                    <label>签订日期</label>
                    <input type="date" class="form-control" name="sign_date" value="${contract.sign_date || ''}">
                </div>
            </div>
            <div class="form-row">
                <div class="form-group">
                    <label>开始日期</label>
                    <input type="date" class="form-control" name="start_date" value="${contract.start_date || ''}">
                </div>
                <div class="form-group">
                    <label>结束日期</label>
                    <input type="date" class="form-control" name="end_date" value="${contract.end_date || ''}">
                </div>
            </div>
            <div class="form-group">
                <label>描述</label>
                <textarea class="form-control" name="description" rows="3">${contract.description || ''}</textarea>
            </div>
            <div class="modal-footer">
                <button type="button" class="btn" onclick="closeModal()">取消</button>
                <button type="submit" class="btn btn-primary">保存</button>
            </div>
        </form>
    `;

    document.getElementById('contractForm').onsubmit = async (e) => {
        e.preventDefault();
        const formData = new FormData(e.target);
        const data = Object.fromEntries(formData);
        data.customer_id = parseInt(data.customer_id);
        data.amount = parseFloat(data.amount);

        if (id) {
            await api.contracts.update(id, data);
        } else {
            await api.contracts.create(data);
        }
        closeModal();
        renderContracts();
    };

    openModal();
}

async function showContractDetail(id) {
    const contract = await api.contracts.get(id);
    let documentInfo = null;
    try {
        documentInfo = await api.contracts.document(id);
    } catch (error) {
        documentInfo = null;
    }

    document.getElementById('modal-title').textContent = '合同详情';
    document.getElementById('modal-body').innerHTML = `
        <div class="detail-grid">
            <div class="detail-item">
                <div class="label">合同编号</div>
                <div class="value">${contract.contract_no}</div>
            </div>
            <div class="detail-item">
                <div class="label">合同标题</div>
                <div class="value">${contract.title}</div>
            </div>
            <div class="detail-item">
                <div class="label">客户</div>
                <div class="value">${contract.customer_name || '-'}</div>
            </div>
            <div class="detail-item">
                <div class="label">信用等级</div>
                <div class="value">${getStatusTag(contract.credit_level)}</div>
            </div>
            <div class="detail-item">
                <div class="label">金额</div>
                <div class="value amount">${formatMoney(contract.amount)}</div>
            </div>
            <div class="detail-item">
                <div class="label">状态</div>
                <div class="value">${getStatusTag(contract.status)}</div>
            </div>
            <div class="detail-item">
                <div class="label">签订日期</div>
                <div class="value">${formatDate(contract.sign_date)}</div>
            </div>
            <div class="detail-item">
                <div class="label">合同期限</div>
                <div class="value">${formatDate(contract.start_date)} 至 ${formatDate(contract.end_date)}</div>
            </div>
        </div>

        <h4 style="margin: 20px 0 10px">Word合同文档</h4>
        ${documentInfo && documentInfo.file_name ? `
            <div class="detail-grid">
                <div class="detail-item">
                    <div class="label">文件名</div>
                    <div class="value">${documentInfo.file_name}</div>
                </div>
                <div class="detail-item">
                    <div class="label">文件大小</div>
                    <div class="value">${documentInfo.file_size} 字节</div>
                </div>
                <div class="detail-item">
                    <div class="label">MD5</div>
                    <div class="value">${documentInfo.file_hash}</div>
                </div>
                <div class="detail-item">
                    <div class="label">格式</div>
                    <div class="value">Microsoft Word (.docx)</div>
                </div>
            </div>
            <p style="margin: 10px 0">
                <a class="btn btn-primary" href="${api.contracts.documentDownloadUrl(id)}" target="_blank">下载Word合同</a>
                <button class="btn" onclick="showDocumentText(${id})">查看合同文本</button>
            </p>
        ` : '<p>该合同尚未绑定Word文档。</p>'}

        ${contract.payment_plans && contract.payment_plans.length > 0 ? `
            <h4 style="margin: 20px 0 10px">付款计划</h4>
            <table>
                <thead>
                    <tr>
                        <th>期数</th>
                        <th>金额</th>
                        <th>到期日</th>
                        <th>状态</th>
                        <th>已付金额</th>
                    </tr>
                </thead>
                <tbody>
                    ${contract.payment_plans.map(p => `
                        <tr>
                            <td>第${p.plan_no}期</td>
                            <td>${formatMoney(p.amount)}</td>
                            <td>${formatDate(p.due_date)}</td>
                            <td>${getStatusTag(p.status)}</td>
                            <td>${formatMoney(p.paid_amount)}</td>
                        </tr>
                    `).join('')}
                </tbody>
            </table>
        ` : ''}

        ${contract.invoices && contract.invoices.length > 0 ? `
            <h4 style="margin: 20px 0 10px">发票记录</h4>
            <table>
                <thead>
                    <tr>
                        <th>发票号</th>
                        <th>金额</th>
                        <th>税额</th>
                        <th>总额</th>
                        <th>开票日期</th>
                        <th>状态</th>
                    </tr>
                </thead>
                <tbody>
                    ${contract.invoices.map(i => `
                        <tr>
                            <td>${i.invoice_no}</td>
                            <td>${formatMoney(i.amount)}</td>
                            <td>${formatMoney(i.tax_amount)}</td>
                            <td>${formatMoney(i.total_amount)}</td>
                            <td>${formatDate(i.issue_date)}</td>
                            <td>${getStatusTag(i.status)}</td>
                        </tr>
                    `).join('')}
                </tbody>
            </table>
        ` : ''}

        <div class="modal-footer">
            <button class="btn" onclick="closeModal()">关闭</button>
        </div>
    `;

    openModal();
}

async function showDocumentText(id) {
    const data = await api.contracts.documentText(id);
    document.getElementById('modal-title').textContent = data.file_name || '合同文本';
    document.getElementById('modal-body').innerHTML = `
        <pre style="white-space: pre-wrap; line-height: 1.7; max-height: 70vh; overflow: auto">${data.text}</pre>
        <div class="modal-footer">
            <button class="btn" onclick="showContractDetail(${id})">返回合同详情</button>
        </div>
    `;
}

// ==================== 付款管理 ====================

async function renderPayments() {
    const contracts = await api.contracts.list();

    let allPayments = [];
    for (const contract of contracts.items) {
        const payments = await api.payments.list(contract.id);
        allPayments = allPayments.concat(payments.items.map(p => ({
            ...p,
            contract_no: contract.contract_no,
            contract_title: contract.title,
        })));
    }

    document.getElementById('content').innerHTML = `
        <div class="card">
            <div class="card-header">
                <h3>付款计划</h3>
            </div>
            <div class="card-body">
                <div class="table-container">
                    <table>
                        <thead>
                            <tr>
                                <th>合同编号</th>
                                <th>期数</th>
                                <th>金额</th>
                                <th>到期日</th>
                                <th>状态</th>
                                <th>已付金额</th>
                                <th>操作</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${allPayments.map(p => `
                                <tr>
                                    <td>${p.contract_no}</td>
                                    <td>第${p.plan_no}期</td>
                                    <td>${formatMoney(p.amount)}</td>
                                    <td>${formatDate(p.due_date)}</td>
                                    <td>${getStatusTag(p.status)}</td>
                                    <td>${formatMoney(p.paid_amount)}</td>
                                    <td>
                                        ${p.status !== 'paid' ? `<button class="btn btn-success" onclick="markPaid(${p.id}, ${p.amount})">确认付款</button>` : '-'}
                                    </td>
                                </tr>
                            `).join('')}
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
    `;
}

async function markPaid(id, amount) {
    if (confirm(`确认收到款项 ${formatMoney(amount)}？`)) {
        await api.payments.pay(id, amount);
        renderPayments();
    }
}

// ==================== 发票管理 ====================

async function renderInvoices() {
    const contracts = await api.contracts.list();

    let allInvoices = [];
    for (const contract of contracts.items) {
        const invoices = await api.invoices.list(contract.id);
        allInvoices = allInvoices.concat(invoices.items.map(i => ({
            ...i,
            contract_no: contract.contract_no,
            contract_title: contract.title,
        })));
    }

    document.getElementById('content').innerHTML = `
        <div class="card">
            <div class="card-header">
                <h3>发票列表</h3>
            </div>
            <div class="card-body">
                <div class="table-container">
                    <table>
                        <thead>
                            <tr>
                                <th>发票号</th>
                                <th>合同编号</th>
                                <th>金额</th>
                                <th>税额</th>
                                <th>总额</th>
                                <th>开票日期</th>
                                <th>状态</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${allInvoices.map(i => `
                                <tr>
                                    <td>${i.invoice_no}</td>
                                    <td>${i.contract_no}</td>
                                    <td>${formatMoney(i.amount)}</td>
                                    <td>${formatMoney(i.tax_amount)}</td>
                                    <td class="amount">${formatMoney(i.total_amount)}</td>
                                    <td>${formatDate(i.issue_date)}</td>
                                    <td>${getStatusTag(i.status)}</td>
                                </tr>
                            `).join('')}
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
    `;
}

// ==================== 模态框 ====================

function openModal() {
    document.getElementById('modal').classList.remove('hidden');
}

function closeModal() {
    document.getElementById('modal').classList.add('hidden');
}

// ==================== 初始化 ====================

document.addEventListener('DOMContentLoaded', () => {
    // 更新时间
    function updateTime() {
        document.getElementById('current-time').textContent = new Date().toLocaleString('zh-CN');
    }
    updateTime();
    setInterval(updateTime, 1000);

    // 菜单点击
    document.querySelectorAll('.menu-item').forEach(item => {
        item.addEventListener('click', (e) => {
            e.preventDefault();
            showPage(item.dataset.page);
        });
    });

    // 加载首页
    showPage('dashboard');
});
