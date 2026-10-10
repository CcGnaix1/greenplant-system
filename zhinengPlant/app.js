// app.js —— 全局状态与登录（MOCK=false 时走真实后端 /auth/wechat）
const req = require('./utils/request')

// ==================== 【接收项目后必须检查】 ====================
// 微信开发者工具模拟器：可使用 http://127.0.0.1:8081/api
// 手机真机调试：必须改成运行 Java 后端电脑的局域网 IP，手机与电脑需连接同一 Wi-Fi。
// 示例：http://192.168.1.100:8081/api
const BACKEND_BASE_URL = 'http://192.168.137.216:8081/api'

App({
  onLaunch() {
    // 读取本地登录态。真实环境：wx.login -> 后端 code2session -> JWT
    const token = wx.getStorageSync('token')
    this.globalData.token = token || ''
    this.globalData.userInfo = wx.getStorageSync('userInfo') || null
  },

  // 登录：MOCK=true 本地假登录；MOCK=false 调后端 /auth/wechat 换 JWT
  login(user) {
    const name = (user && user.name) || '绿植主人'
    return new Promise((resolve, reject) => {
      if (req.MOCK) {
        const token = 'mock-token-' + Date.now()
        const info = Object.assign({ id: 1, name: '绿植主人', familyId: 1, role: 'owner' }, user)
        wx.setStorageSync('token', token)
        wx.setStorageSync('userInfo', info)
        this.globalData.token = token
        this.globalData.userInfo = info
        resolve(info)
        return
      }
      wx.login({
        success: loginRes => {
          if (!loginRes.code) {
            reject(new Error('微信未返回登录凭证'))
            return
          }
          wx.request({
            url: this.globalData.baseUrl + '/auth/wechat',
            method: 'POST',
            data: { code: loginRes.code, nickname: name },
            success: res => {
              const body = res.data
              if (body && body.code === 0) {
                resolve(this.saveSession(body.data))
              } else {
                reject(new Error((body && body.msg) || '登录失败'))
              }
            },
            fail: reject
          })
        },
        fail: reject
      })
    })
  },

  // 手机号密码登录，可与微信登录在登录页自由切换。
  phoneLogin(credentials) {
    if (req.MOCK) {
      const info = { id: 2, name: credentials.nickname || '手机用户', familyId: 0, role: 'owner' }
      const token = 'mock-phone-token-' + Date.now()
      return Promise.resolve(this.saveSession({ token, user: {
        id: info.id, nickname: info.name, familyId: info.familyId, role: info.role
      }}))
    }
    return this.authRequest('/auth/login', {
      phone: credentials.phone,
      password: credentials.password
    })
  },

  // 手机号注册成功后后端会直接返回登录令牌，无需再次登录。
  phoneRegister(account) {
    if (req.MOCK) {
      return this.phoneLogin(account)
    }
    return this.authRequest('/auth/register', {
      phone: account.phone,
      password: account.password,
      nickname: account.nickname
    })
  },

  authRequest(path, data) {
    return new Promise((resolve, reject) => {
      wx.request({
        url: this.globalData.baseUrl + path,
        method: 'POST',
        data,
        success: res => {
          const body = res.data
          if (body && body.code === 0) {
            resolve(this.saveSession(body.data))
          } else {
            reject(new Error((body && body.msg) || '登录失败'))
          }
        },
        fail: err => reject(new Error((err && err.errMsg) || '无法连接登录服务'))
      })
    })
  },

  saveSession(data) {
    const u = data.user
    const storedAvatar = u.avatarUrl || ''
    const avatarUrl = storedAvatar && !/^https?:\/\//.test(storedAvatar)
      ? this.globalData.baseUrl.replace(/\/api\/?$/, '') + storedAvatar
      : storedAvatar
    const info = { id: u.id, name: u.nickname, familyId: u.familyId || 0, role: u.role || 'owner', avatarUrl }
    wx.setStorageSync('token', data.token)
    wx.setStorageSync('userInfo', info)
    this.globalData.token = data.token
    this.globalData.userInfo = info
    return info
  },

  // 兼容旧调用：mockLogin = login
  mockLogin(user) {
    return this.login(user)
  },

  logout() {
    wx.removeStorageSync('token')
    wx.removeStorageSync('userInfo')
    this.globalData.token = ''
    this.globalData.userInfo = null
  },

  globalData: {
    token: '',
    userInfo: null,
    baseUrl: BACKEND_BASE_URL
  }
})
