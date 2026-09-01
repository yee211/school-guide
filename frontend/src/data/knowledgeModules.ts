import { BookOpen, Building2, ClipboardList, GraduationCap, House, TrendingUp } from 'lucide-vue-next'

// 与 backend/data/raw 中的资料主题对应；这里只维护提问入口，不缓存招生答案。
// 新增知识资料时同步维护模块、问题及来源，不根据系统年份推断数据覆盖范围。
export const knowledgeModules = [
  {
    id: 'overview', label: '学校概况', icon: Building2,
    description: '了解学校沿革、办学定位、师资与产教融合。',
    sources: ['school_overview.md', '长沙工业学院基本信息.md'],
    questions: ['请介绍一下长沙工业学院的基本情况', '长沙工业学院的历史沿革是怎样的？', '学校的师资和实验实训条件怎么样？', '学校在产教融合方面有哪些合作？'],
  },
  {
    id: 'majors', label: '学院专业', icon: GraduationCap,
    description: '从二级学院到专业设置，了解学科方向和选科要求。',
    sources: ['长沙工业学院基本信息.md', '长沙工业学院2026年招生计划.md'],
    questions: ['长沙工业学院有哪些二级学院和专业？', '学校有哪些特色专业？', '2026年湖南物理类有哪些招生专业及选科要求？', '2026年湖南历史类有哪些招生专业？'],
  },
  {
    id: 'admissions', label: '招生与学费', icon: ClipboardList,
    description: '查询知识库中的招生计划、专业人数和学费，提问时请说明年份、省份及科类。',
    sources: ['长沙工业学院2024年拟招生本科专业及人数.md', '长沙工业学院2025年湖南省招生计划.md', '长沙工业学院2025年外省分专业计划.md', '长沙工业学院2026年招生计划.md'],
    questions: ['2026年湖南物理类计算机科学与技术专业招多少人？', '2026年湖南物理类软件工程专业学费是多少？', '2025年长沙工业学院在外省有哪些招生计划？', '2026年湖南历史类会计学专业的招生人数和学费是多少？'],
  },
  {
    id: 'scores', label: '录取分数', icon: TrendingUp,
    description: '按年份、省份、科类查询投档分和位次；专业组投档线不等于专业录取线。',
    sources: ['长沙工业学院历年录取分数线汇总.md', 'CIT2425省内投档线.md', 'CIT2026省内投档线.md'],
    questions: ['2026年湖南历史类第102组的投档分和最低位次是多少？', '2026年湖南物理类第107组的投档分和最低位次是多少？', '2025年湖南物理类各专业组投档线是多少？', '2024年湖南历史类投档线是多少？'],
  },
  {
    id: 'life', label: '校园生活', icon: House,
    description: '宿舍、食堂、校园网与到校交通；生活资料仅作参考，具体安排以学校通知为准。',
    sources: ['school_life.txt'],
    questions: ['学校宿舍是几人间，有哪些设施？', '学校食堂和快递站在哪里？', '学校宿舍的校园网和用电情况怎么样？', '从长沙火车南站到学校怎么走？'],
  },
  {
    id: 'library', label: '图书馆服务', icon: BookOpen,
    description: '了解开放时间、自习空间、借阅规则及移动图书馆。',
    sources: ['library.md'],
    questions: ['学校图书馆的开放时间和自习条件怎么样？', '学生最多能借几本书，借期多长？', '如何使用图书馆自助借还机？', '如何使用学校的超星移动图书馆？'],
  },
] as const

export type KnowledgeModuleId = typeof knowledgeModules[number]['id']
