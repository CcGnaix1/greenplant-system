// pages/create/create.js
const api = require('../../utils/request')

Page({
  data: {
    species: '',
    name: '',
    family: '客厅',
    env: { temp: '18~28℃', humidity: '60%', light: '散射光', waterInterval: '5~7 天' }
  },
  onLoad(opt) {
    if (opt.species) {
      this.setData({ species: decodeURIComponent(opt.species), name: decodeURIComponent(opt.species) })
    }
  },
  onSpecies(e) { this.setData({ species: e.detail.value }) },
  onName(e) { this.setData({ name: e.detail.value }) },
  onFamily(e) { this.setData({ family: e.detail.value }) },
  submit() {
    const name = this.data.name || this.data.species || '未命名植物'
    if (api.MOCK) {
      wx.showToast({ title: '建档成功', icon: 'success' })
      setTimeout(() => wx.navigateBack(), 700)
      return
    }
    // 真实模式：按品种名查 id，再调 POST /plants 建档
    const keyword = this.data.species || name
    wx.showLoading({ title: '建档中' })
    api.call('/knowledge/list')
      .then(res => {
        const list = res.data || []
        const hit = list.find(k => k.name === keyword) || list.find(k => k.name.includes(keyword))
        return api.call('/plant/create', {
          data: {
            name,
            speciesId: hit ? hit.id : 1, // 未匹配到品种时默认绿萝
            potMaterial: this.data.family === '客厅' ? '陶瓷' : '塑料',
            initHeightCm: 10,
            emotionTag: '新成员'
          }
        })
      })
      .then(() => {
        wx.hideLoading()
        wx.showToast({ title: '建档成功', icon: 'success' })
        setTimeout(() => wx.navigateBack(), 700)
      })
      .catch(err => {
        wx.hideLoading()
        wx.showToast({ title: (err && err.message) || '建档失败', icon: 'none' })
      })
  }
})
