// pages/plan/plan.js
const api = require('../../utils/request')

Page({
  data: { message: '', list: [] },
  onShow() {
    Promise.all([api.call('/notification/list'), api.call('/plant/list')]).then(([nRes, pRes]) => {
      const plants = pRes.data || []
      return Promise.all(plants.map(p => api.call('/plant/care-plan', { data: { id: p.id } })))
        .then(planResults => {
          const plans = planResults.reduce((all, r) => all.concat(r.data || []), [])
          const first = plans[0]
          const message = first
            ? `${first.plantName}：${first.suggestion}，下次日期 ${first.nextDueDate || '待安排'}`
            : '暂时没有待执行的养护计划'
          this.setData({ list: nRes.data || [], message })
        })
    }).catch(err => wx.showToast({ title: err.message || '计划加载失败', icon: 'none' }))
  },
  markRead(e) {
    const id = e.currentTarget.dataset.id
    api.call('/notification/read', { data: { id } }).then(() => this.onShow())
      .catch(err => wx.showToast({ title: err.message || '操作失败', icon: 'none' }))
  }
})
