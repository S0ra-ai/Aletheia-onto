/**
 * 合同管理系统 - API 层
 */
const API_BASE = 'http://localhost:8001/api';

const api = {
    // 客户 API
    customers: {
        list: () => fetch(`${API_BASE}/customers`).then(r => r.json()),
        get: (id) => fetch(`${API_BASE}/customers/${id}`).then(r => r.json()),
        create: (data) => fetch(`${API_BASE}/customers`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data),
        }).then(r => r.json()),
        update: (id, data) => fetch(`${API_BASE}/customers/${id}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data),
        }).then(r => r.json()),
    },

    // 合同 API
    contracts: {
        list: (params = {}) => {
            const query = new URLSearchParams(params).toString();
            return fetch(`${API_BASE}/contracts${query ? '?' + query : ''}`).then(r => r.json());
        },
        get: (id) => fetch(`${API_BASE}/contracts/${id}`).then(r => r.json()),
        create: (data) => fetch(`${API_BASE}/contracts`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data),
        }).then(r => r.json()),
        update: (id, data) => fetch(`${API_BASE}/contracts/${id}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data),
        }).then(r => r.json()),
        updateStatus: (id, status, comment) => fetch(`${API_BASE}/contracts/${id}/status?status=${status}${comment ? '&comment=' + encodeURIComponent(comment) : ''}`, {
            method: 'POST',
        }).then(r => r.json()),
        recent: async (limit = 5) => {
            const data = await fetch(`${API_BASE}/contracts`).then(r => r.json());
            return { items: (data.items || []).slice(0, limit) };
        },
        document: (id) => fetch(`${API_BASE}/contracts/${id}/document`).then(r => r.json()),
        documentText: (id) => fetch(`${API_BASE}/contracts/${id}/document/text`).then(r => r.json()),
        documentDownloadUrl: (id) => `${API_BASE}/contracts/${id}/document/download`,
    },

    // 付款 API
    payments: {
        list: (contractId) => fetch(`${API_BASE}/contracts/${contractId}/payments`).then(r => r.json()),
        create: (data) => fetch(`${API_BASE}/payments`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data),
        }).then(r => r.json()),
        pay: (id, amount) => fetch(`${API_BASE}/payments/${id}/pay?paid_amount=${amount}`, {
            method: 'POST',
        }).then(r => r.json()),
    },

    // 发票 API
    invoices: {
        list: (contractId) => fetch(`${API_BASE}/contracts/${contractId}/invoices`).then(r => r.json()),
        create: (data) => fetch(`${API_BASE}/invoices`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data),
        }).then(r => r.json()),
    },

    // 统计 API
    dashboard: {
        stats: () => fetch(`${API_BASE}/dashboard/stats`).then(r => r.json()),
    },
};
