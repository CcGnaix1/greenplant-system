// utils/mock.js —— mock 数据层（接口就绪后由 request.js 切换为真实请求）
// 覆盖：植物档案 / 养护记录 / 识别结果 / 诊断 / 知识库 / 家庭 / 任务 / 提醒

const plants = [
  {
    id: 1,
    name: '龟背竹',
    species: '龟背竹',
    familyName: '客厅大盆',
    tag: '茁壮成长',
    status: 'ok',          // ok / dry / warn
    dryDays: 2,
    nextDue: '今天 18:00',
    cover: '龟',
    env: { temp: '18~28℃', humidity: '60%', light: '散射光', waterInterval: '5~7 天' },
    heightCm: 86,
    recordCount: 42
  },
  {
    id: 2,
    name: '虎皮兰',
    species: '虎皮兰',
    familyName: '书房小盆',
    tag: '土壤偏干',
    status: 'dry',
    dryDays: 9,
    nextDue: '建议今天浇水',
    cover: '虎',
    env: { temp: '15~30℃', humidity: '40%', light: '耐阴', waterInterval: '10~14 天' },
    heightCm: 42,
    recordCount: 18
  },
  {
    id: 3,
    name: '绿萝',
    species: '绿萝',
    familyName: '阳台垂吊',
    tag: '叶尖发黄',
    status: 'warn',
    dryDays: 3,
    nextDue: '明天浇水',
    cover: '绿',
    env: { temp: '16~28℃', humidity: '65%', light: '半阴', waterInterval: '3~5 天' },
    heightCm: 30,
    recordCount: 27
  }
]

const records = {
  1: [
    { id: 101, type: 'water', text: '浇水 500ml', member: '我', time: '今天 09:20' },
    { id: 102, type: 'fertilize', text: '施营养液 20ml', member: '妈妈', time: '3 天前' },
    { id: 103, type: 'prune', text: '修剪黄叶 2 片', member: '我', time: '1 周前' },
    { id: 104, type: 'rotate', text: '转盆 180°', member: '爸爸', time: '2 周前' }
  ],
  2: [
    { id: 201, type: 'water', text: '沿盆边少量补水', member: '我', time: '9 天前' }
  ],
  3: [
    { id: 301, type: 'water', text: '浇水 300ml', member: '妈妈', time: '3 天前' },
    { id: 302, type: 'check', text: '检查叶尖，建议通风', member: '我', time: '昨天' }
  ]
}

// 诊断症状标签库
const symptomTags = [
  '叶片发黄', '叶尖干枯', '叶片发软下垂', '长斑/病斑',
  '叶片卷曲', '土壤发白/板结', '有虫害', '整体萎蔫'
]

// 识别结果（mock：拍照后返回候选）
const recognizeResult = {
  candidates: [
    { species: '龟背竹', confidence: 0.94, desc: '天南星科，喜温暖湿润，耐半阴' },
    { species: '春羽', confidence: 0.41, desc: '相似品种，叶片裂叶形态略小' },
    { species: '橡皮树', confidence: 0.18, desc: '差异较大，仅供参考' }
  ],
  confidence: 0.94,
  highConfidence: true
}

// 诊断报告（mock）
const diagnoseReport = {
  likely: '叶尖干枯 + 疑似红蜘蛛',
  cause: '近期浇水偏少、空气干燥，叶尖失水干枯；叶背可见细小红点，疑似红蜘蛛初期',
  urgent: '今天先浇水一次并向叶面喷雾增湿；3 天内连续观察叶背',
  longTerm: '建议将浇水频率提高到 3~5 天一次，定期用湿布擦拭叶面，保持通风',
  confidence: 0.78
}

// 知识库
const knowledgeList = [
  { id: 1, name: '龟背竹', tag: '热门', cover: '龟', desc: '耐阴好养，叶片开裂' },
  { id: 2, name: '绿萝', tag: '新手', cover: '绿', desc: '水培土培皆可，净化空气' },
  { id: 3, name: '虎皮兰', tag: '耐旱', cover: '虎', desc: '半月一浇，省心耐阴' },
  { id: 4, name: '多肉植物', tag: '多肉', cover: '肉', desc: '少浇水多晒太阳' },
  { id: 5, name: '发财树', tag: '热门', cover: '发', desc: '怕积水，宁干勿湿' },
  { id: 6, name: '兰花', tag: '进阶', cover: '兰', desc: '讲究植料与通风' }
]

const knowledgeDetail = {
  habit: '喜温暖湿润和半阴环境，忌强光直射，适宜温度 18~28℃。',
  seasons: ['春：生长期，保持湿润', '夏：多喷雾增湿', '秋：减少浇水', '冬：控水防冻'],
  water: '表土下 2cm 干了再浇透，约 5~7 天一次，冬季拉长间隔。',
  fertilize: '生长季每月 1~2 次稀薄液肥，冬季停肥。',
  breed: '春季换盆时分株，或扦插茎段。',
  faq: [
    { q: '叶子不开裂怎么办？', a: '多为光照不足或苗龄偏小，增加散射光。' },
    { q: '叶尖发黑？', a: '多为积水烂根或空气过干，先控水并检查根系。' }
  ]
}

// 家庭协作
const family = {
  name: '我家绿植圈',
  members: [
    { id: 1, name: '我', role: 'owner', duty: '总负责' },
    { id: 2, name: '妈妈', role: 'member', duty: '日常浇水' },
    { id: 3, name: '爸爸', role: 'member', duty: '转盆/修剪' }
  ],
  tasks: [
    { id: 1, title: '给龟背竹浇水', plant: '龟背竹', assignee: '妈妈', due: '今天', done: false },
    { id: 2, title: '检查绿萝叶背虫害', plant: '绿萝', assignee: '我', due: '今天', done: false },
    { id: 3, title: '虎皮兰换盆', plant: '虎皮兰', assignee: '爸爸', due: '本周末', done: true }
  ]
}

// 提醒/通知
const notifications = [
  { id: 1, title: '虎皮兰该浇水了', time: '今天 08:30', read: false },
  { id: 2, title: '妈妈完成了龟背竹浇水', time: '今天 09:21', read: false },
  { id: 3, title: '绿萝叶尖发黄，建议诊断', time: '昨天 20:10', read: true }
]

module.exports = {
  plants, records, symptomTags, recognizeResult, diagnoseReport,
  knowledgeList, knowledgeDetail, family, notifications
}
