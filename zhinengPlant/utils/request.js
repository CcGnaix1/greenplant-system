// utils/request.js —— 接口层（统一处理 mock ↔ 真实后端切换）
// MOCK = true  ：返回本地假数据（模拟 {code,msg,data} 契约）
// MOCK = false ：请求真实后端（app.js 的 baseUrl），自动把页面用的 mock 路径翻译成后端路径
const mock = require('./mock')
const { imageFor } = require('./plant-images')

const MOCK = false

// 统一返回结构：{ code:0, msg:'ok', data }
function ok(data) { return { code: 0, msg: 'ok', data } }
function delay(data, ms = 300) {
  return new Promise(resolve => setTimeout(() => resolve(ok(data)), ms))
}

// ============ 真实请求 ============

// 数据适配：把后端返回结构补成页面期望的字段（cover/nextDue/familyName 等）
function adapt(path, body) {
  const data = body && body.data
  if (path === '/plant/list' && Array.isArray(data)) {
    body.data = data.map(p => ({
      id: p.id, name: p.name, species: p.species,
      cover: (p.name || '植')[0],
      familyName: p.species,
      tag: p.tag || 'ok',
      status: p.status || 'ok',
      recordCount: p.recordCount || 0,
      heightCm: p.heightCm,
      nextDue: p.lastWaterAt ? '上次 ' + String(p.lastWaterAt).slice(5, 16) : '尚未浇水',
      image: imageFor(p.species)
    }))
  }
  if (path === '/plant/detail' && data) {
    data.cover = (data.name || '植')[0]
    data.familyName = data.species
    data.nextDue = data.lastWaterAt ? '上次 ' + String(data.lastWaterAt).slice(5, 16) : '尚未浇水'
    data.image = imageFor(data.species)
    if (!data.recordCount) data.recordCount = 0
  }
  return body
}

// mock 路径 → 后端真实路径（对齐 docs/API接口文档.md）
function realOf(path, opts = {}) {
  const id = opts.data ? opts.data.id : null
  switch (path) {
    case '/plant/list': return { url: '/plants', method: 'GET' }
    case '/plant/detail': return { url: '/plants/' + id, method: 'GET' }
    case '/plant/records': return { url: '/plants/' + id + '/timeline', method: 'GET' }
    case '/plant/create': return { url: '/plants', method: 'POST' }
    case '/plant/water': return { url: '/plants/' + id + '/watering', method: 'POST' }
    case '/plant/record': return { url: '/plants/' + id + '/records', method: 'POST' }
    case '/plant/stats': return { url: '/plants/' + id + '/stats', method: 'GET' }
    case '/plant/care-plan': return { url: '/plants/' + id + '/care-plan', method: 'GET' }
    case '/species/recognize': return { url: '/species/recognize', method: 'POST', upload: true, name: 'image' }
    case '/diagnose/submit': return { url: '/diagnosis', method: 'POST', upload: true, name: 'image' }
    case '/diagnose/feedback': return { url: '/diagnosis/' + id + '/feedback', method: 'POST' }
    case '/knowledge/list': return { url: '/knowledge/search', method: 'GET' }
    case '/knowledge/detail': return { url: '/knowledge/species/' + id, method: 'GET' }
    case '/family/info': return { url: '/family/info', method: 'GET', composite: true }
    case '/family/create': return { url: '/family', method: 'POST' }
    case '/family/member/add': return { url: '/family/' + opts.data.familyId + '/members', method: 'POST' }
    case '/family/task/create': return { url: '/family/' + opts.data.familyId + '/tasks', method: 'POST' }
    case '/family/task/mine': return { url: '/family/' + opts.data.familyId + '/tasks', method: 'GET' }
    case '/family/task/complete': return { url: '/family/tasks/' + id + '/complete', method: 'PATCH' }
    case '/family/task/toggle': return { url: '/family/tasks/' + id + '/done', method: 'PATCH' }
    case '/notification/list': return { url: '/notifications', method: 'GET' }
    case '/notification/read': return { url: '/notifications/' + id + '/read', method: 'PATCH' }
    case '/user/avatar': return { url: '/user/avatar', method: 'POST', upload: true, name: 'avatar' }
    case '/export/records': return { url: '/export/records', method: 'GET' }
    default: return { url: path, method: 'GET' }
  }
}

// 真实请求（JSON）
function realRequest(path, { method = 'GET', data } = {}) {
  const a = getApp()
  return new Promise((resolve, reject) => {
    wx.request({
      url: a.globalData.baseUrl + path,
      method,
      data,
      header: { Authorization: 'Bearer ' + a.globalData.token },
      success: res => {
        const body = res.data
        if (body && body.code === 0) resolve(body)
        else reject(new Error((body && body.msg) || '请求失败'))
      },
      fail: reject
    })
  })
}

// 真实上传（识别 / 诊断：multipart 图片字段）
function realUpload(path, { image, uploadName = 'image' } = {}) {
  const a = getApp()
  return new Promise((resolve, reject) => {
    if (!image) return reject(new Error('缺少图片'))
    wx.uploadFile({
      url: a.globalData.baseUrl + path,
      filePath: image,
      name: uploadName,
      header: { Authorization: 'Bearer ' + a.globalData.token },
      success: res => {
        try {
          const body = JSON.parse(res.data)
          if (body.code === 0) resolve(body)
          else reject(new Error(body.msg || '识别失败'))
        } catch (e) {
          reject(new Error('返回格式异常'))
        }
      },
      fail: reject
    })
  })
}

// 家庭信息组合接口：members + tasks 拼成页面需要的结构
function realFamily() {
  const a = getApp()
  const fid = (a.globalData.userInfo && a.globalData.userInfo.familyId) || 0
  const empty = { familyId: 0, name: '我的家庭', members: [], tasks: [] }
  if (!fid) return Promise.resolve(ok(empty))
  const h = { Authorization: 'Bearer ' + a.globalData.token }
  return new Promise((resolve, reject) => {
    wx.request({
      url: a.globalData.baseUrl + '/family/' + fid + '/members', method: 'GET', header: h,
      success: mRes => wx.request({
        url: a.globalData.baseUrl + '/family/' + fid + '/tasks', method: 'GET', header: h,
        success: tRes => {
          resolve(ok({
            familyId: fid,
            name: '我的家庭',
            members: (mRes.data && mRes.data.data) || [],
            tasks: (tRes.data && tRes.data.data) || []
          }))
        },
        fail: reject
      }),
      fail: reject
    })
  })
}

// 统一入口：页面调用 api.call(mockPath, opts)
// opts.image 存在时走上传（识别/诊断）；否则按翻译路径发请求
function call(path, opts = {}) {
  if (MOCK) return mockRouter(path, opts)
  const t = realOf(path, opts)
  if (t.upload) return realUpload(t.url, Object.assign({}, opts, { uploadName: t.name || 'image' })).then(body => adapt(path, body))
  if (t.composite) return realFamily()
  return realRequest(t.url, { method: t.method, data: opts.data }).then(body => adapt(path, body))
}

// ============ mock 路由（数据在 utils/mock.js） ============
function mockRouter(path, opts = {}) {
  switch (path) {
    case '/plant/list': return delay(mock.plants)
    case '/plant/detail': return delay(mock.plants.find(p => p.id === opts.data.id) || mock.plants[0])
    case '/plant/records': return delay(mock.records[opts.data.id] || [])
    case '/plant/create': return delay({ id: 99 })
    case '/plant/water': return delay({ careRecordId: 1 })
    case '/species/recognize': return delay(mock.recognizeResult, 900) // 模拟识别耗时
    case '/diagnose/submit': return delay(mock.diagnoseReport, 1200)
    case '/diagnose/feedback': return delay({ diagnosisId: opts.data.id, feedback: true })
    case '/knowledge/list': return delay(mock.knowledgeList)
    case '/knowledge/detail': return delay(mock.knowledgeDetail)
    case '/family/info': return delay(mock.family)
    case '/family/member/add': return delay({ userId: 2, nickname: '家庭成员' })
    case '/family/task/mine': return delay(mock.family.tasks.filter(t => !t.done))
    case '/family/task/complete': return delay({ taskId: opts.data.id, done: true })
    case '/notification/list': return delay(mock.notifications)
    default: return delay({})
  }
}

module.exports = { call, MOCK }
