// pages/login/login.js
const app = getApp()

Page({
  data: {
    method: 'wechat',
    name: '',
    phone: '',
    password: '',
    isRegister: false,
    loading: false
  },
  switchMethod(e) {
    if (this.data.loading) return
    this.setData({ method: e.currentTarget.dataset.method })
  },
  onInput(e) { this.setData({ name: e.detail.value }) },
  onPhone(e) { this.setData({ phone: e.detail.value.replace(/\D/g, '').slice(0, 11) }) },
  onPassword(e) { this.setData({ password: e.detail.value }) },
  toggleRegister() {
    if (this.data.loading) return
    this.setData({ isRegister: !this.data.isRegister })
  },
  doLogin() {
    if (this.data.loading) return
    this.setData({ loading: true })
    app.login({ name: this.data.name || '绿植主人' })
      .then(() => {
        this.finishLogin('微信登录成功')
      })
      .catch(err => {
        wx.showToast({ title: err.message || '登录失败', icon: 'none' })
        this.setData({ loading: false })
      })
  },
  doPhoneLogin() {
    if (this.data.loading) return
    const phone = this.data.phone.trim()
    const password = this.data.password
    if (!/^1\d{10}$/.test(phone)) {
      wx.showToast({ title: '请输入正确的11位手机号', icon: 'none' })
      return
    }
    if (!password) {
      wx.showToast({ title: '请输入密码', icon: 'none' })
      return
    }
    if (this.data.isRegister && password.length < 6) {
      wx.showToast({ title: '密码至少需要6位', icon: 'none' })
      return
    }
    this.setData({ loading: true })
    const action = this.data.isRegister
      ? app.phoneRegister({ phone, password, nickname: this.data.name.trim() || '绿植主人' })
      : app.phoneLogin({ phone, password })
    action.then(() => this.finishLogin(this.data.isRegister ? '注册成功' : '登录成功'))
      .catch(err => {
        wx.showToast({ title: err.message || '登录失败', icon: 'none' })
        this.setData({ loading: false })
      })
  },
  finishLogin(title) {
    this.setData({ loading: false })
    wx.showToast({ title, icon: 'success' })
    setTimeout(() => {
      if (getCurrentPages().length > 1) wx.navigateBack()
      else wx.reLaunch({ url: '/pages/home/home' })
    }, 600)
  }
})
