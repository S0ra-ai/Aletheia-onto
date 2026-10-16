/**
 * demo —— 页面：pages/demo/DemoCenter.tsx
 *
 * 待迁移：本页面的中文文案填到这里，页面里改用 `t('demo.…')`。
 */
import type { MessageEntry } from './shell';

export const demo: Record<string, MessageEntry> = {
  'title': { zh: '演示中心', en: 'Demo' },
  'subtitle': { zh: '一键加载演示数据，体验完整业务流程', en: 'Load sample data in one click and walk through a full business flow' },

  'notice.title': { zh: '演示说明', en: 'About the demo' },
  'notice.body': { zh: '点击下方按钮将自动创建样例数据库、注册数据源、执行元数据扫描并生成领域本体草案。', en: 'The button below creates a sample database, registers it as a data source, runs a metadata scan and drafts a domain ontology.' },

  'contract.title': { zh: '合同管理演示', en: 'Contract management demo' },
  'contract.intro': { zh: '演示合同管理场景，包含：', en: 'Demonstrates the contract-management scenario, including:' },
  'contract.objects': { zh: '客户、合同、付款计划、发票等业务对象', en: 'Business objects such as customers, contracts, payment schedules and invoices' },
  'contract.risks': { zh: '黑名单客户、逾期付款等风险场景', en: 'Risk cases such as blacklisted customers and overdue payments' },
  'contract.rules': { zh: '合同金额校验、付款逾期预警等规则', en: 'Rules such as contract-amount validation and overdue-payment alerts' },
  'contract.start': { zh: '启动合同管理演示', en: 'Start the contract demo' },

  'equipment.title': { zh: '设备运维演示', en: 'Equipment maintenance demo' },
  'equipment.intro': { zh: '演示设备运维场景，包含：', en: 'Demonstrates the equipment-maintenance scenario, including:' },
  'equipment.objects': { zh: '设备、工单、点检记录、备件等业务对象', en: 'Business objects such as equipment, work orders, inspection records and spare parts' },
  'equipment.risks': { zh: '重要设备未关闭工单、备件库存不足等风险', en: 'Risks such as open work orders on critical equipment and low spare-part stock' },
  'equipment.rules': { zh: '设备状态校验、备件库存预警等规则', en: 'Rules such as equipment-status validation and spare-part stock alerts' },
  'equipment.start': { zh: '启动设备运维演示', en: 'Start the equipment demo' },

  'loadFailed': { zh: '加载演示数据失败', en: 'Could not load the demo data' },

  'successTitle': { zh: '演示数据加载成功', en: 'Demo data loaded' },
  'resultWithDecision': {
    zh: '数据源 {id} 已接入，本体已生成，并对样例实例完成了一次研判：{decision}',
    en: 'Data source {id} is connected, the ontology is generated, and one assessment has run over the sample instances: {decision}',
  },
  'resultWithoutDecision': { zh: '数据源ID: {id}，本体已生成', en: 'Data source ID: {id}; the ontology is generated' },

  'viewDatasource': { zh: '查看数据源', en: 'View the data source' },
  'viewOntology': { zh: '查看本体', en: 'View the ontology' },
  'trySemantic': { zh: '体验语义服务', en: 'Try the semantic service' },
};
