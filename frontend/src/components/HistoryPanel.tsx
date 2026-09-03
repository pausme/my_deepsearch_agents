import {
  FileDoneOutlined,
  FilePdfOutlined,
  HistoryOutlined,
  HomeOutlined,
  PlusOutlined
} from "@ant-design/icons";
import {
  Button,
  Descriptions,
  Drawer,
  Empty,
  Form,
  Input,
  InputNumber,
  List,
  Modal,
  Select,
  Tag,
  Typography
} from "antd";
import { useCallback, useState } from "react";
import {
  createRenovationSession,
  getReportContent,
  getReportDetail,
  listRenovationSessions,
  listSessionReports
} from "../lib/api";
import type { RenovationReport, RenovationSession, RiskItem } from "../types";
import { MarkdownRenderer } from "./MarkdownRenderer";
import { API_BASE_URL } from "../lib/config";

const RISK_TAG_COLOR: Record<string, string> = {
  HIGH: "red",
  MEDIUM: "orange",
  LOW: "green"
};

const STAGE_OPTIONS = [
  { value: "INITIAL", label: "准备阶段（还没定装修公司）" },
  { value: "QUOTE_REVIEW", label: "看报价阶段" },
  { value: "CONTRACT_REVIEW", label: "签合同阶段" },
  { value: "CONSTRUCTION", label: "施工中" },
  { value: "SOFT_FURNISH", label: "软装收尾" }
];

interface HistoryPanelProps {
  activeSessionId: string;
  onSessionBound: (sessionId: string) => void;
}

export function HistoryPanel({ activeSessionId, onSessionBound }: HistoryPanelProps) {
  const [historyOpen, setHistoryOpen] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);
  const [sessions, setSessions] = useState<RenovationSession[]>([]);
  const [reports, setReports] = useState<RenovationReport[]>([]);
  const [selectedSession, setSelectedSession] = useState<RenovationSession | null>(null);
  const [reportDetail, setReportDetail] = useState<{
    report: RenovationReport;
    risks: RiskItem[];
    markdown: string;
  } | null>(null);
  const [loading, setLoading] = useState(false);
  const [form] = Form.useForm();

  const openHistory = useCallback(async () => {
    setHistoryOpen(true);
    setLoading(true);
    try {
      const data = await listRenovationSessions();
      setSessions(data.sessions);
    } finally {
      setLoading(false);
    }
  }, []);

  const openSessionReports = useCallback(async (session: RenovationSession) => {
    setSelectedSession(session);
    setLoading(true);
    try {
      const data = await listSessionReports(session.session_id);
      setReports(data.reports);
    } finally {
      setLoading(false);
    }
  }, []);

  const openReportDetail = useCallback(async (report: RenovationReport) => {
    setLoading(true);
    try {
      const [detail, content] = await Promise.all([
        getReportDetail(report.report_id),
        getReportContent(report.report_id)
      ]);
      setReportDetail({
        report: detail.report,
        risks: detail.risk_items,
        markdown: content.markdown
      });
    } finally {
      setLoading(false);
    }
  }, []);

  const handleCreateSession = useCallback(async () => {
    const values = await form.validateFields();
    const data = await createRenovationSession({
      city: values.city,
      house_area: values.house_area,
      room_type: values.room_type,
      renovation_stage: values.renovation_stage,
      district: values.district || "",
      budget_min: values.budget_min ?? null,
      budget_max: values.budget_max ?? null,
      priority_tags: values.priority_tags || [],
      delivery_date: values.delivery_date || ""
    });
    onSessionBound(data.session_id);
    setCreateOpen(false);
    form.resetFields();
  }, [form, onSessionBound]);

  return (
    <>
      <div className="sidebar-section renovation-panel">
        <span className="sidebar-label">RENOVATION</span>
        {activeSessionId ? (
          <Tag color="green" style={{ marginBottom: 8 }}>
            已绑定装修会话
          </Tag>
        ) : (
          <Tag style={{ marginBottom: 8 }}>未绑定会话</Tag>
        )}
        <Button
          block
          icon={<PlusOutlined />}
          onClick={() => setCreateOpen(true)}
          style={{ marginBottom: 8 }}
        >
          新建装修会话
        </Button>
        <Button block icon={<HistoryOutlined />} onClick={openHistory}>
          历史分析
        </Button>
      </div>

      {/* 新建装修会话 */}
      <Modal
        cancelButtonProps={{ size: "small" }}
        cancelText="取消"
        okText="创建会话"
        onCancel={() => setCreateOpen(false)}
        onOk={handleCreateSession}
        open={createOpen}
        title="新建装修分析会话"
      >
        <Form form={form} layout="vertical">
          <Form.Item
            label="城市"
            name="city"
            rules={[{ required: true, message: "请填写城市" }]}
          >
            <Input placeholder="如：杭州" />
          </Form.Item>
          <Form.Item label="区县（可选）" name="district">
            <Input placeholder="如：滨江区" />
          </Form.Item>
          <Form.Item
            label="房屋面积（㎡）"
            name="house_area"
            rules={[{ required: true, message: "请填写建筑面积" }]}
          >
            <InputNumber min={10} max={1000} style={{ width: "100%" }} />
          </Form.Item>
          <Form.Item
            label="房型"
            name="room_type"
            rules={[{ required: true, message: "请填写房型" }]}
          >
            <Input placeholder="如：三室两厅一卫" />
          </Form.Item>
          <Form.Item
            initialValue="QUOTE_REVIEW"
            label="当前装修阶段"
            name="renovation_stage"
          >
            <Select options={STAGE_OPTIONS} />
          </Form.Item>
          <Form.Item label="预算下限（元，可选）" name="budget_min">
            <InputNumber min={0} step={10000} style={{ width: "100%" }} placeholder="如 150000" />
          </Form.Item>
          <Form.Item label="预算上限（元，可选）" name="budget_max">
            <InputNumber min={0} step={10000} style={{ width: "100%" }} placeholder="如 180000" />
          </Form.Item>
          <Form.Item label="关注重点（可选）" name="priority_tags">
            <Select
              allowClear
              mode="multiple"
              options={[
                { value: "省钱", label: "省钱" },
                { value: "颜值", label: "颜值" },
                { value: "环保", label: "环保" },
                { value: "工期", label: "工期" },
                { value: "耐用", label: "耐用" }
              ]}
              placeholder="可多选"
            />
          </Form.Item>
        </Form>
      </Modal>

      {/* 历史分析抽屉 */}
      <Drawer
        onClose={() => {
          setHistoryOpen(false);
          setSelectedSession(null);
          setReportDetail(null);
        }}
        open={historyOpen}
        title={
          selectedSession ? `报告列表 · ${selectedSession.city}` : "历史装修分析"
        }
        width={560}
      >
        {!selectedSession ? (
          <List
            dataSource={sessions}
            loading={loading}
            locale={{ emptyText: <Empty description="还没有装修会话，先新建一个吧" /> }}
            renderItem={(session) => (
              <List.Item
                actions={[
                  <Button
                    key="open"
                    onClick={() => openSessionReports(session)}
                    size="small"
                    type="link"
                  >
                    查看报告
                  </Button>
                ]}
              >
                <List.Item.Meta
                  avatar={<HomeOutlined style={{ fontSize: 20 }} />}
                  description={`${session.create_time} · ${session.room_type}`}
                  title={`${session.city} ${session.house_area}㎡ · ${
                    session.report_count ?? 0
                  } 份报告`}
                />
              </List.Item>
            )}
          />
        ) : reportDetail ? (
          <div>
            <Button
              onClick={() => setReportDetail(null)}
              size="small"
              style={{ marginBottom: 12 }}
              type="link"
            >
              ← 返回报告列表
            </Button>
            <Descriptions
              column={1}
              size="small"
              title={reportDetail.report.title}
            >
              <Descriptions.Item label="报告编号">
                {reportDetail.report.report_id}
              </Descriptions.Item>
              <Descriptions.Item label="生成时间">
                {reportDetail.report.create_time}
              </Descriptions.Item>
              {reportDetail.report.budget_score != null ? (
                <Descriptions.Item label="预算健康度">
                  {reportDetail.report.budget_score} / 100
                </Descriptions.Item>
              ) : null}
            </Descriptions>

            {reportDetail.risks.length > 0 ? (
              <div className="risk-block">
                <Typography.Title level={5}>风险清单</Typography.Title>
                {reportDetail.risks.map((risk) => (
                  <div className="risk-item" key={risk.id}>
                    <Tag color={RISK_TAG_COLOR[risk.risk_level] || "default"}>
                      {risk.risk_level}
                    </Tag>
                    <strong>{risk.title}</strong>
                    <p>{risk.suggestion}</p>
                  </div>
                ))}
              </div>
            ) : null}

            {reportDetail.report.markdown_path ? (
              <Button
                href={getReportPdfUrl(reportDetail.report.markdown_path)}
                icon={<FilePdfOutlined />}
                size="small"
                style={{ margin: "12px 0" }}
                target="_blank"
              >
                下载 PDF 报告
              </Button>
            ) : null}

            <MarkdownRenderer content={reportDetail.markdown} />
          </div>
        ) : (
          <List
            dataSource={reports}
            loading={loading}
            locale={{ emptyText: <Empty description="该会话还没有生成报告" /> }}
            renderItem={(report) => (
              <List.Item
                actions={[
                  <Button
                    key="open"
                    onClick={() => openReportDetail(report)}
                    size="small"
                    type="link"
                  >
                    查看详情
                  </Button>
                ]}
              >
                <List.Item.Meta
                  avatar={<FileDoneOutlined style={{ fontSize: 20 }} />}
                  description={`${report.create_time} · ${report.task_id}`}
                  title={`${report.title}${report.budget_score != null ? `（预算健康度 ${report.budget_score}）` : ""}`}
                />
              </List.Item>
            )}
          />
        )}
      </Drawer>
    </>
  );
}

function getReportPdfUrl(markdownPath: string): string {
  // PDF 与 Markdown 同名同目录，走通用下载接口；同源部署时 API_BASE_URL 为空
  const pdfPath = markdownPath.replace(/\.md$/, ".pdf");
  const url = new URL(`${API_BASE_URL}/api/download`, window.location.origin);
  url.searchParams.set("path", pdfPath);
  return url.toString();
}
